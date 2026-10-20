using System.Numerics;
using System.Security.Cryptography;
using System.Text.Json;
using JoltPhysicsSharp;
using MapDrive;

// PHYSICAL COMPONENT: unlike DriverLogicUnits, this calls actual native Jolt
// on naturally settled production BattleTank bodies, never injected speeds.
internal static class MovingReverseChecks
{
    sealed record Sample(float Speed,float PreSpeed,float Motor,float Brake,int Gear,float Clutch,float Rpm,string Sha);
    sealed record Run(string EntrySha,float EntrySpeed,Sample[] Frames,string TraceSha);
    static readonly BattleSceneInput.Control Stop=new(0,0,true,100);
    static string Sha(byte[] value)=>Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant();
    static void Need(bool value,string code){if(!value)throw new InvalidDataException("actual moving reversal: "+code);}
    static Run Measure(BattleSceneInput.Manifest manifest,string kind,int steps,int prefix,int initialDirection,bool enabled,int grade=0)
    {
        using var pairs=new ObjectLayerPairFilterTable(2);pairs.EnableCollision(0,1);pairs.EnableCollision(1,1);
        using var broad=new BroadPhaseLayerInterfaceTable(2,2);broad.MapObjectToBroadPhaseLayer(0,0);broad.MapObjectToBroadPhaseLayer(1,1);
        using var filter=new ObjectVsBroadPhaseLayerFilterTable(broad,2,pairs,2);
        using var jobs=new InlineJobSystem();
        using var world=new PhysicsSystem(new PhysicsSystemSettings{MaxBodies=32,MaxBodyPairs=8192,MaxContactConstraints=8192,
            ObjectLayerPairFilter=pairs,BroadPhaseLayerInterface=broad,ObjectVsBroadPhaseLayerFilter=filter});
        float slope=MathF.Tan(grade*MathF.PI/180);
        Vector3[] vertices=[new(-500,-500*slope,-500),new(500,-500*slope,-500),new(-500,500*slope,500),new(500,500*slope,500)];
        IndexedTriangle[] triangles=[new(0,2,3),new(0,3,1)];
        using var meshSettings=new MeshShapeSettings(vertices.AsSpan(),triangles.AsSpan());using var shape=new MeshShape(meshSettings);
        using var floorSettings=new BodyCreationSettings(shape,Vector3.Zero,Quaternion.Identity,MotionType.Static,0){Friction=1};
        var floor=world.BodyInterface.CreateBody(floorSettings);world.BodyInterface.AddBody(floor.ID,Activation.DontActivate);
        BattleTank? tank=null;
        try
        {
            var actor=manifest.Actors.Single(a=>a.Kind==kind)with{Slot=0,Spawn=new Vector3(0,3,0),Yaw=0};
            tank=new BattleTank(world,actor,null,true,enabled);world.OptimizeBroadPhase();
            var controller=tank.Constraint.GetController<TrackedVehicleController>();
            Sample Capture(float preSpeed)
            {
                var q=tank.Body.Rotation;var v=tank.Body.GetLinearVelocity();var p=tank.Body.Position;var a=tank.Body.GetAngularVelocity();
                var engine=controller.Engine;var gear=controller.Transmission;
                var values=new List<float>{p.X,p.Y,p.Z,q.X,q.Y,q.Z,q.W,v.X,v.Y,v.Z,a.X,a.Y,a.Z,
                    controller.ForwardInput,controller.LeftRatio,controller.RightRatio,controller.BrakeInput,engine.CurrentRPM,
                    gear.CurrentGear,gear.CurrentRatio,gear.ClutchFriction,controller.LeftTrack.AngularVelocity,controller.RightTrack.AngularVelocity};
                for(int i=0;i<6;i++)
                {var wheel=tank.Constraint.GetWheel(i);values.AddRange([wheel.HasContact?1:0,wheel.SuspensionLambda,wheel.LongitudinalLambda,wheel.LateralLambda]);}
                Need(values.All(float.IsFinite),"nonfinite state");
                return new Sample(Vector3.Dot(v,Vector3.Transform(Vector3.UnitZ,q)),preSpeed,controller.ForwardInput,controller.BrakeInput,
                    gear.CurrentGear,gear.ClutchFriction,engine.CurrentRPM,Sha(JsonSerializer.SerializeToUtf8Bytes(values)));
            }
            Sample Step(BattleSceneInput.Control command,int tick)
            {
                float preSpeed=Vector3.Dot(tank.Body.GetLinearVelocity(),Vector3.Transform(Vector3.UnitZ,tank.Body.Rotation));
                tank.BeforeStep(command,(tick-1)%6+1,false);var error=world.Update(1f/60,steps,jobs);jobs.CheckThread();
                Need(error==PhysicsUpdateError.None,"Jolt update error");tank.AfterStep();return Capture(preSpeed);
            }
            // Steep authored fixtures get a fixed bounded ten-second STOP
            // settle; use the same production acceptance, never fewer supports.
            int settleTicks=grade==0?180:600;
            for(int tick=1;tick<=settleTicks;tick++)Step(Stop,tick);tank.CheckSettled();
            var launch=new BattleSceneInput.Control(initialDirection,0,false,100);
            for(int tick=1;tick<=prefix;tick++)Step(launch,tick);
            var entry=Capture(0);if(grade==0)Need(initialDirection*entry.Speed>.5f,"moving reversal not exercised");
            var reverse=new BattleSceneInput.Control(-initialDirection,0,false,100);var frames=new Sample[480];
            for(int tick=1;tick<=frames.Length;tick++)frames[tick-1]=Step(reverse,prefix+tick);
            return new Run(entry.Sha,entry.Speed,frames,Sha(JsonSerializer.SerializeToUtf8Bytes(frames.Select(f=>f.Sha))));
        }
        finally{tank?.Dispose();world.BodyInterface.RemoveAndDestroyBody(floor.ID);}
    }
    public static object RunAll(BattleSceneInput.Manifest manifest,string output)
    {
        var rows=new List<object>();int runs=0,firstBrakeFramesExact=0,fullTraceExact=0,replayExact=0;
        foreach(string kind in new[]{"ms1","is7"})foreach(int steps in new[]{1,4})foreach(int prefix in new[]{90,480})foreach(int direction in new[]{-1,1})
        {
            var before=Measure(manifest,kind,steps,prefix,direction,false);var after=Measure(manifest,kind,steps,prefix,direction,true);runs+=2;
            Need(before.EntrySha==after.EntrySha,"entry state differs");Need(before.Frames[0].Brake==1&&after.Frames[0].Brake==1,"first opposed request not braking");
            int exit=Array.FindIndex(after.Frames,f=>f.Brake==0);Need(exit>0,"first brake did not exit");
            for(int i=0;i<=exit;i++){Need(before.Frames[i].Sha==after.Frames[i].Sha,"first accepted reversal phase changed");firstBrakeFramesExact++;}
            // Flat moving reversals should not roll back after exiting their
            // first brake phase; therefore they remain complete old/new controls.
            Need(before.TraceSha==after.TraceSha,"flat moving reversal regressed");fullTraceExact++;
            Need(after.Frames[exit].Motor*-direction>0,"old-direction motor retained after brake");
            int crossing=Array.FindIndex(after.Frames,f=>f.Speed*-direction>=.1f);Need(crossing>=0,"opposite motion not reached");
            Need(after.Frames.All(f=>MathF.Abs(f.Motor)<=1&&f.Brake is >=0 and <=1),"actuator bounds");
            var replay=Measure(manifest,kind,steps,prefix,direction,true);runs++;Need(replay.TraceSha==after.TraceSha,"same-build physical replay changed");replayExact++;
            rows.Add(new{kind,steps,prefix,initial_direction=direction,entry_speed=after.EntrySpeed,
                brake_exit_tick=exit+1,moving_opposite_tick=crossing+1,brake_exit_seconds=(exit+1)/60.0,
                moving_opposite_seconds=(crossing+1)/60.0,baseline_trace=before.TraceSha,candidate_trace=after.TraceSha,
                baseline_final_speed=before.Frames[^1].Speed,candidate_final_speed=after.Frames[^1].Speed,
                brake_exit_gear=after.Frames[exit].Gear,brake_exit_clutch=after.Frames[exit].Clutch,brake_exit_rpm=after.Frames[exit].Rpm});
        }
        using(var flat=new FileStream(Path.Combine(output,"flat-result.json"),FileMode.CreateNew))
            JsonSerializer.Serialize(flat,new{status="PASS_ACTUAL_FLAT_REVERSAL",actual_world_runs=runs,
                first_brake_exact_frames=firstBrakeFramesExact,full_flat_trace_exact=fullTraceExact,replay_exact=replayExact,rows},new JsonSerializerOptions{WriteIndented=true});
        var slopes=new List<object>();
        foreach(string kind in new[]{"ms1","is7"})foreach(int steps in new[]{1,4})foreach(int grade in new[]{16,21})
        {
            var before=Measure(manifest,kind,steps,0,-1,false,grade);var after=Measure(manifest,kind,steps,0,-1,true,grade);runs+=2;
            Need(before.EntrySha==after.EntrySha,"slope entry differs");
            int rollback=0,oldBrake=0,oldBrakeEntries=0,newBrake=0;
            for(int i=0;i<after.Frames.Length;i++)
            {
                var b=before.Frames[i];var a=after.Frames[i];
                if(b.Brake>0){oldBrake++;if(i==0||before.Frames[i-1].Brake==0)oldBrakeEntries++;}
                if(a.Brake>0)newBrake++;
                // These cases start from natural near-rest. Once the initial
                // intent's brake has exited, a held W cannot arm a new brake.
                if(after.EntrySpeed>=-.5f && a.PreSpeed<-.5f)
                {rollback++;Need(a.Brake==0&&a.Motor>0,"held W rollback braked/reset");}
            }
            if(after.EntrySpeed>=-.5f)Need(newBrake==0,"slope false rearm without input edge");
            var replay=Measure(manifest,kind,steps,0,-1,true,grade);runs++;Need(replay.TraceSha==after.TraceSha,"slope replay changed");replayExact++;
            slopes.Add(new{kind,steps,grade,settle_stop_ticks=600,entry_speed=after.EntrySpeed,rollback_steps=rollback,
                rollback_scope=rollback>0?"EXERCISED_ACTUAL":"NOT_EXERCISED_NOT_A_ROLLBACK_PROOF",old_brake_steps=oldBrake,
                old_brake_entries=oldBrakeEntries,new_brake_steps=newBrake,baseline_final_speed=before.Frames[^1].Speed,
                candidate_final_speed=after.Frames[^1].Speed,baseline_trace=before.TraceSha,candidate_trace=after.TraceSha,
                hill_climb_acceptance="NOT_REQUIRED: no claim every profile can climb this grade"});
        }
        return new{status="PASS_ACTUAL_JOLT_COMPONENT",actual_world_runs=runs,first_brake_exact_frames=firstBrakeFramesExact,
            full_flat_trace_exact=fullTraceExact,replay_exact=replayExact,body_pose_or_velocity_setters_after_spawn=0,
            terrain="authored flat and uniform16/21deg planes, not original map",native_client="NOT_RUN",rows,slopes};
    }
}
