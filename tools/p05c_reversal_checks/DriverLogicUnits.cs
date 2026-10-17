using System.Numerics;
using JoltPhysicsSharp;
using MapDrive;

// DRIVER-LOGIC UNIT ONLY: signedSpeed is a supplied metric, never measured
// motion. Real native controller readbacks prove actuator/state transitions;
// no PhysicsSystem.Update is called and no physical traction claim is made.
internal static class DriverLogicUnits
{
    sealed class Rig : IDisposable
    {
        readonly ObjectLayerPairFilterTable pairs = new(2);
        readonly BroadPhaseLayerInterfaceTable broad = new(2,2);
        readonly ObjectVsBroadPhaseLayerFilterTable filter;
        readonly PhysicsSystem world;
        readonly BoxShape shape;
        readonly Body body;
        readonly WheelSettingsTV[] wheels;
        readonly VehicleConstraint constraint;
        readonly TrackedHandling handling;
        public readonly TrackedVehicleController Controller;
        public readonly float Forward, Reverse;
        public Rig(BattleSceneInput.Actor actor, bool enabled)
        {
            pairs.EnableCollision(0,1); pairs.EnableCollision(1,1); broad.MapObjectToBroadPhaseLayer(0,0); broad.MapObjectToBroadPhaseLayer(1,1);
            filter = new ObjectVsBroadPhaseLayerFilterTable(broad,2,pairs,2);
            world = new PhysicsSystem(new PhysicsSystemSettings { MaxBodies=8, MaxBodyPairs=32, MaxContactConstraints=32,
                ObjectLayerPairFilter=pairs, BroadPhaseLayerInterface=broad, ObjectVsBroadPhaseLayerFilter=filter });
            var c=actor.Config; float N(string key)=>c.GetProperty(key).GetSingle();
            Forward=N("max_forward_mps"); Reverse=N("max_reverse_mps");
            var center=CheckedInput.Vector(c.GetProperty("body_center_offset"),-5,5);
            var points=c.GetProperty("wheel_points").EnumerateArray().Select(x=>CheckedInput.Vector(x,-5,5)).ToArray();
            wheels=points.Select(p=>new WheelSettingsTV { Position=p-center, SuspensionDirection=-Vector3.UnitY,
                WheelUp=Vector3.UnitY, WheelForward=Vector3.UnitZ, SuspensionMinLength=N("suspension_min"),
                SuspensionMaxLength=N("suspension_max"), Radius=N("wheel_radius"), Width=.25f,
                LongitudinalFriction=N("longitudinal_friction"), LateralFriction=N("lateral_friction") }).ToArray();
            shape=new BoxShape(actor.Binding.HalfExtents);
            using var bodySettings=TrackedBodySettings.Create(shape,N("mass_kg"),new Vector3(0,3,0),Quaternion.Identity);
            body=world.BodyInterface.CreateBody(bodySettings); world.BodyInterface.AddBody(body.ID,Activation.Activate);
            using var settings=new TrackedVehicleControllerSettings();
            settings.SetTrack(0,new VehicleTrackSettings { DrivenWheel=1,Wheels=[0,1,2],MaxBrakeTorque=N("track_max_brake_torque"),Inertia=TrackedHandling.TrackInertia(N("mass_kg"),N("wheel_radius")) });
            settings.SetTrack(1,new VehicleTrackSettings { DrivenWheel=4,Wheels=[3,4,5],MaxBrakeTorque=N("track_max_brake_torque"),Inertia=TrackedHandling.TrackInertia(N("mass_kg"),N("wheel_radius")) });
            constraint=new VehicleConstraint(body,new VehicleConstraintSettings { Up=Vector3.UnitY,Forward=Vector3.UnitZ,Wheels=wheels,Controller=settings });
            Controller=constraint.GetController<TrackedVehicleController>();
            handling=new TrackedHandling(MathF.Abs(points[3].X-points[0].X),c.GetProperty("handling").GetProperty("max_yaw_rate_rad_s").GetSingle(),N("mass_kg"),wheels,false,enabled);
            handling.VerifyWheelSettings(constraint);
        }
        public void Apply(float speed,int throttle,int steer=0,bool brake=false,int percent=100) =>
            handling.Apply(Controller,speed,0,throttle,steer,brake,Forward*percent/100,Reverse*percent/100,1f/60);
        public float[] Read()=>[Controller.ForwardInput,Controller.LeftRatio,Controller.RightRatio,Controller.BrakeInput];
        public void Dispose()
        {
            constraint.Dispose(); world.BodyInterface.RemoveAndDestroyBody(body.ID); foreach(var wheel in wheels)wheel.Dispose();
            shape.Dispose(); world.Dispose(); filter.Dispose(); broad.Dispose(); pairs.Dispose();
        }
    }
    public static object Run(BattleSceneInput.Manifest manifest)
    {
        int assertions=0,applications=0;var completed=new List<string>();
        void Need(bool ok,string code){assertions++;if(!ok)throw new InvalidDataException("driver logic: "+code);}
        void Apply(Rig r,float speed,int throttle,int steer=0,bool brake=false,int percent=100){r.Apply(speed,throttle,steer,brake,percent);applications++;}
        foreach(string kind in new[]{"ms1","is7"})
        {
            var actor=manifest.Actors.Single(a=>a.Kind==kind);
            // A continuously held raw intent never acquires a new brake just
            // because measured speed crosses the opposite-speed threshold.
            using(var r=new Rig(actor,true))
            {
                Apply(r,0,1);
                for(int i=0;i<192;i++)
                {
                    float speed=i%3==0?-.50001f:i%3==1?-.5f:-.2f;
                    Apply(r,speed,1,i%3-1,false,i%3==0?25:i%3==1?50:100);
                    Need(r.Controller.BrakeInput==0 && r.Controller.ForwardInput>0,"held W/steer/cruise rearmed");
                }
                completed.Add(kind+": repeated W six-step/32-packet model");
            }
            // Same sequence is a useful negative control against old policy.
            using(var old=new Rig(actor,false))
            { Apply(old,0,1);Apply(old,-.50001f,1);Need(old.Controller.BrakeInput==1 && old.Controller.ForwardInput==0,"old-policy negative control missing"); }
            foreach(int direction in new[]{-1,1})
            {
                using var r=new Rig(actor,true);
                Apply(r,0,0); Apply(r,-direction*.50001f,direction);
                Need(r.Controller.BrakeInput==1 && r.Controller.ForwardInput==0,"new opposed intent did not arm");
                Apply(r,-direction*.51f,direction);Need(r.Controller.BrakeInput==1,"latch lost before old boundary");
                Apply(r,-direction*.5f,direction);Need(r.Controller.BrakeInput==0 && direction*r.Controller.ForwardInput>0,"old -0.5 exit changed");
                Apply(r,-direction*.7f,direction);Need(r.Controller.BrakeInput==0 && direction*r.Controller.ForwardInput>0,"held intent rearmed after exit");
                Apply(r,0,0);Apply(r,-direction*.7f,direction);Need(r.Controller.BrakeInput==1,"release then new press failed to rearm");
                Apply(r,-direction*2,-direction);Need(r.Controller.BrakeInput==0 && direction*r.Controller.ForwardInput<0,"changed intent retained old latch/sign");
                completed.Add(kind+": direction "+direction+" boundary/exit/release/switch");
            }
            using(var r=new Rig(actor,true))
            {
                Apply(r,0,0);Apply(r,-.5f,1);Need(r.Controller.BrakeInput==0,"exact arm threshold not strict");
                Apply(r,-.50001f,1);Need(r.Controller.BrakeInput==0,"boundary miss rearmed held request");
                Apply(r,r.Forward,1);Need(r.Controller.ForwardInput==0 && r.Controller.BrakeInput==0,"speed cap changed");
                Apply(r,-.8f,1);Need(r.Controller.ForwardInput>0 && r.Controller.BrakeInput==0,"governor cut became input edge");
            }
            using(var r=new Rig(actor,true))
            {
                Apply(r,-2,1);Need(r.Controller.BrakeInput==1,"arm for cancellation");
                Apply(r,-2,0,1);Need(r.Controller.BrakeInput==0,"coast release did not clear latch");
                Apply(r,-2,1);Need(r.Controller.BrakeInput==1,"new W after coast did not arm");
                Apply(r,-2,0,0,true);Need(r.Controller.BrakeInput==1 && r.Controller.ForwardInput==0,"explicit Stop actuator changed");
                Apply(r,2,-1);Need(r.Controller.BrakeInput==1,"new S after Stop did not arm");
                Apply(r,-2,1);Need(r.Controller.BrakeInput==1,"intent switch failed to replace with newly opposed latch");
                Apply(r,.1f,1);Need(r.Controller.BrakeInput==0 && r.Controller.ForwardInput>0,"overshoot release missed");
            }
            using(var r=new Rig(actor,true))
            {
                Apply(r,0,1);var before=r.Read();
                foreach(var bad in new Action[]{()=>r.Apply(-2,-2),()=>r.Apply(-2,1,0,true),()=>r.Apply(float.NaN,-1)})
                { bool rejected=false;try{bad();}catch(InvalidDataException){rejected=true;}Need(rejected && r.Read().SequenceEqual(before),"invalid input mutated actuator"); }
                Apply(r,-2,1);Need(r.Controller.BrakeInput==0,"invalid input consumed raw intent state");
            }
            using(var r=new Rig(actor,true))
            {
                for(int i=0;i<40;i++)
                {int intent=i%2==0?1:-1;Apply(r,intent*2,intent);Need(r.Controller.BrakeInput==0 && intent*r.Controller.ForwardInput>0 && MathF.Abs(r.Controller.ForwardInput)<=4f/60+1e-6f,"rapid flip sign/ramp bound");}
            }
        }
        return new {status="PASS_DRIVER_LOGIC_ONLY",physical_traction="NOT_RUN_BY_UNIT",physics_update_calls=0,assertions,applications,completed};
    }
}
