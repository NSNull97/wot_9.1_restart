using System.Numerics;
using System.Text.Json;
using System.Security.Cryptography;
using JoltPhysicsSharp;
using MapDrive;

// Separate authored hill-entry check. No cold spawn on the inclined slab,
// no injected body pose/velocity, and no universal hill-climb requirement.
internal static class RampFreshIntentChecks
{
    sealed record Frame(float PreSpeed,float Speed,float Motor,float Brake,float Rpm,int Gear,float Clutch,float Height,float Z,string Sha);
    sealed record Run(string Status,int CoastTicks,string PrefixSha,Frame[] Fresh,string TraceSha,string TracePath,float FreshEntrySpeed);
    static readonly BattleSceneInput.Control Stop=new(0,0,true,100),Drive=new(1,0,false,100),Coast=new(0,0,false,100);
    static string Sha(byte[] bytes)=>Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void Need(bool value,string code){if(!value)throw new InvalidDataException(code);}
    static Run Measure(BattleSceneInput.Manifest manifest,string kind,int steps,int grade,bool enabled,string folder)
    {
        using var pairs=new ObjectLayerPairFilterTable(2);pairs.EnableCollision(0,1);pairs.EnableCollision(1,1);
        using var broad=new BroadPhaseLayerInterfaceTable(2,2);broad.MapObjectToBroadPhaseLayer(0,0);broad.MapObjectToBroadPhaseLayer(1,1);
        using var filter=new ObjectVsBroadPhaseLayerFilterTable(broad,2,pairs,2);using var jobs=new InlineJobSystem();
        using var world=new PhysicsSystem(new PhysicsSystemSettings{MaxBodies=32,MaxBodyPairs=8192,MaxContactConstraints=8192,
            ObjectLayerPairFilter=pairs,BroadPhaseLayerInterface=broad,ObjectVsBroadPhaseLayerFilter=filter});
        float height=80*MathF.Tan(grade*MathF.PI/180);
        Vector3[] vertices=[new(-30,0,-150),new(30,0,-150),new(-30,0,0),new(30,0,0),new(-30,height,80),new(30,height,80),new(-30,height,150),new(30,height,150)];
        IndexedTriangle[] triangles=[new(0,2,3),new(0,3,1),new(2,4,5),new(2,5,3),new(4,6,7),new(4,7,5)];
        using var meshSettings=new MeshShapeSettings(vertices.AsSpan(),triangles.AsSpan());using var shape=new MeshShape(meshSettings);
        using var floorSettings=new BodyCreationSettings(shape,Vector3.Zero,Quaternion.Identity,MotionType.Static,0){Friction=1};
        var floor=world.BodyInterface.CreateBody(floorSettings);world.BodyInterface.AddBody(floor.ID,Activation.DontActivate);
        Directory.CreateDirectory(folder);string path=Path.Combine(folder,"trace.jsonl");
        using var trace=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.Read);long bytes=0;int tick=0;
        BattleTank? tank=null;
        try
        {
            var actor=manifest.Actors.Single(a=>a.Kind==kind)with{Slot=0,Spawn=new Vector3(0,3,-30),Yaw=0};
            var center=CheckedInput.Vector(actor.Config.GetProperty("body_center_offset"),-5,5);
            tank=new BattleTank(world,actor,null,true,enabled);world.OptimizeBroadPhase();var controller=tank.Constraint.GetController<TrackedVehicleController>();
            var prefix=new List<string>();var full=new List<string>();
            float Speed()=>Vector3.Dot(tank.Body.GetLinearVelocity(),Vector3.Transform(Vector3.UnitZ,tank.Body.Rotation));
            Frame Step(BattleSceneInput.Control command,string phase)
            {
                float pre=Speed();tick++;tank.BeforeStep(command,(tick-1)%6+1,false);
                var result=world.Update(1f/60,steps,jobs);jobs.CheckThread();Need(result==PhysicsUpdateError.None,"native Jolt update fault");tank.AfterStep();
                var q=tank.Body.Rotation;var p=tank.Body.Position;var v=tank.Body.GetLinearVelocity();var a=tank.Body.GetAngularVelocity();
                var gear=controller.Transmission;var engine=controller.Engine;var origin=p-Vector3.Transform(center,q);
                var values=new List<float>{p.X,p.Y,p.Z,q.X,q.Y,q.Z,q.W,v.X,v.Y,v.Z,a.X,a.Y,a.Z,
                    controller.ForwardInput,controller.LeftRatio,controller.RightRatio,controller.BrakeInput,engine.CurrentRPM,
                    gear.CurrentGear,gear.CurrentRatio,gear.ClutchFriction,controller.LeftTrack.AngularVelocity,controller.RightTrack.AngularVelocity};
                for(int i=0;i<6;i++){var wheel=tank.Constraint.GetWheel(i);values.AddRange([wheel.HasContact?1:0,wheel.SuspensionLambda,wheel.LongitudinalLambda,wheel.LateralLambda]);}
                Need(values.All(float.IsFinite),"nonfinite actual ramp state");string hash=Sha(JsonSerializer.SerializeToUtf8Bytes(values));full.Add(hash);
                if(phase!="fresh")prefix.Add(hash);
                var frame=new Frame(pre,Speed(),controller.ForwardInput,controller.BrakeInput,engine.CurrentRPM,gear.CurrentGear,gear.ClutchFriction,origin.Y,origin.Z,hash);
                var raw=JsonSerializer.SerializeToUtf8Bytes(new{tick,phase,state=frame});Need(raw.Length<=4096&&bytes+raw.Length+1<=2*1024*1024,"trace bound");trace.Write(raw);trace.WriteByte(10);bytes+=raw.Length+1;return frame;
            }
            for(int i=0;i<180;i++)Step(Stop,"settle");tank.CheckSettled();
            for(int i=0;i<600;i++)Step(Drive,"drive");
            int coast=0;while(coast<900&&Speed()>=-.6f){Step(Coast,"coast");coast++;}
            float entry=Speed();string prefixHash=Sha(JsonSerializer.SerializeToUtf8Bytes(prefix));
            if(entry>=-.6f)
                return new Run("NOT_EXERCISED_NO_NATURAL_ROLLBACK",coast,prefixHash,[],Sha(JsonSerializer.SerializeToUtf8Bytes(full)),path,entry);
            var frames=new Frame[480];for(int i=0;i<frames.Length;i++)frames[i]=Step(Drive,"fresh");
            return new Run("EXERCISED_FRESH_W_AFTER_ROLLBACK",coast,prefixHash,frames,Sha(JsonSerializer.SerializeToUtf8Bytes(full)),path,entry);
        }
        finally{tank?.Dispose();world.BodyInterface.RemoveAndDestroyBody(floor.ID);}
    }
    public static int Main(string[] args)
    {
        bool initialized=false;string? output=null;
        try
        {
            Need(args.Length==8,"--local-root ROOT --manifest PATH --manifest-sha256 SHA --out FRESH");var fields=new Dictionary<string,string>();
            for(int i=0;i<args.Length;i+=2)Need(fields.TryAdd(args[i],args[i+1]),"duplicate options");
            Need(fields.Keys.Order().SequenceEqual(new[]{"--local-root","--manifest","--manifest-sha256","--out"}),"exact options");
            string root=Path.GetFullPath(fields["--local-root"]);output=Path.GetFullPath(fields["--out"]);
            CheckedInput.Owned(root,Path.GetDirectoryName(output)!);Need(!Directory.Exists(output)&&!File.Exists(output),"fresh output required");
            var manifest=BattleSceneInput.Load(root,fields["--manifest"],fields["--manifest-sha256"]);Directory.CreateDirectory(output);
            Need(Foundation.Init(false),"native Jolt init");initialized=true;var rows=new List<object>();int exercised=0,notExercised=0,unmatched=0,runs=0;
            foreach(string kind in new[]{"ms1","is7"})foreach(int steps in new[]{1,4})foreach(int grade in new[]{16,21})
            {
                string id=kind+"-s"+steps+"-g"+grade;
                var before=Measure(manifest,kind,steps,grade,false,Path.Combine(output,id+"-old"));runs++;
                var after=Measure(manifest,kind,steps,grade,true,Path.Combine(output,id+"-new"));runs++;
                var replay=Measure(manifest,kind,steps,grade,true,Path.Combine(output,id+"-repeat"));runs++;
                Need(replay.TraceSha==after.TraceSha,"same-build ramp replay mismatch");
                if(before.PrefixSha!=after.PrefixSha)
                {
                    unmatched++;rows.Add(new{id,status="NOT_MATCHED_BEFORE_FRESH_W",old_status=before.Status,new_status=after.Status,
                        before.PrefixSha,new_prefix_sha=after.PrefixSha,old_trace=before.TraceSha,new_trace=after.TraceSha});continue;
                }
                if(before.Fresh.Length==0||after.Fresh.Length==0)
                {notExercised++;rows.Add(new{id,status="NOT_EXERCISED_NO_NATURAL_ROLLBACK",entry_speed=after.FreshEntrySpeed,coast_ticks=after.CoastTicks,trace_sha=after.TraceSha});continue;}
                exercised++;Need(before.CoastTicks==after.CoastTicks&&before.FreshEntrySpeed==after.FreshEntrySpeed,"fresh entry mismatch");
                Need(before.Fresh[0].Brake==1&&after.Fresh[0].Brake==1,"fresh opposed W did not arm brake");
                int exit=Array.FindIndex(after.Fresh,f=>f.Brake==0);Need(exit>0,"fresh reversal brake did not exit");
                for(int i=0;i<=exit;i++)Need(before.Fresh[i].Sha==after.Fresh[i].Sha,"first fresh brake phase changed");
                Need(after.Fresh.Skip(exit).All(f=>f.Brake==0),"held W rearmed after first brake phase");
                Need(after.Fresh.Skip(exit).Where(f=>f.PreSpeed<0).All(f=>f.Motor>0),"held W rollback reset motor after first brake");
                rows.Add(new{id,status="PASS_FRESH_INTENT_FIRST_PHASE_AND_NO_REARM",coast_ticks=after.CoastTicks,entry_speed=after.FreshEntrySpeed,
                    first_brake_exit_tick=exit+1,first_phase_exact_frames=exit+1,
                    old_brake_steps=before.Fresh.Count(f=>f.Brake>0),new_brake_steps=after.Fresh.Count(f=>f.Brake>0),
                    old_final_speed=before.Fresh[^1].Speed,new_final_speed=after.Fresh[^1].Speed,
                    old_height_delta=before.Fresh[^1].Height-before.Fresh[0].Height,new_height_delta=after.Fresh[^1].Height-after.Fresh[0].Height,
                    old_trace=before.TraceSha,new_trace=after.TraceSha});
            }
            bool passed=exercised==8&&notExercised==0&&unmatched==0&&runs==24;
            using var file=new FileStream(Path.Combine(output,"result.json"),FileMode.CreateNew);
            JsonSerializer.Serialize(file,new{schema="p05c-ramp-fresh-intent-checks.v1",status=passed?"PASS":"FAIL_INCOMPLETE_RAMP_COVERAGE",
                actual_native_jolt=true,world_runs=runs,exercised,not_exercised=notExercised,not_matched=unmatched,
                geometry="8 shared vertices/6 upward triangles: flat -150..0,16/21deg ramp0..80,plateau80..150; width60m",
                controls="180 STOP settle,600 W,up to900 neutral coast until v<-.6,480 freshW",body_pose_or_velocity_setters_after_spawn=0,
                native_client="NOT_RUN",hill_climb_acceptance="NOT_REQUIRED",rows},new JsonSerializerOptions{WriteIndented=true});return passed?0:1;
        }
        catch(Exception ex)
        {
            Console.Error.WriteLine(ex);if(output!=null&&Directory.Exists(output))
            {using var file=new FileStream(Path.Combine(output,"failure.json"),FileMode.CreateNew);JsonSerializer.Serialize(file,new{status="FAIL_RETAINED",type=ex.GetType().Name,error=ex.Message});}return 1;
        }
        finally{if(initialized)Foundation.Shutdown();}
    }
}
