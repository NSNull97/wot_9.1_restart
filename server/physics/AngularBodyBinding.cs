using System.Numerics;
using System.Text.Json;
using JoltPhysicsSharp;

namespace MapDrive;

// The gateway authenticates the complete source profile SHA. The worker can
// independently check its complete physical projection and actual getter bits.
// Neither a mass match nor this lookup authenticates a foreign loadout.
internal sealed class AngularBodyBinding
{
    public string Kind { get; }
    public string ProfileSha256 { get; }
    public float MassKg { get; }
    public Vector3 HalfExtents { get; }
    public float InverseMass { get; }
    public Vector3 PrincipalInverse { get; }
    public Quaternion InertiaRotation { get; }
    static float F(uint bits) => BitConverter.UInt32BitsToSingle(bits);
    AngularBodyBinding(string kind, string sha, float massKg, Vector3 half, uint mass, uint x, uint y, uint z)
    {
        Kind=kind;
        ProfileSha256=sha;MassKg=massKg;HalfExtents=half;InverseMass=F(mass);
        PrincipalInverse=new(F(x),F(y),F(z));InertiaRotation=new(F(0x3f3504f3),F(0x3f3504f3),0,0);
    }
    // Exact double projection matches the source-profile loader; actual physics
    // inputs are subsequently converted to f32 once by the existing config path.
    const string Ms1 = """
    {"handling":{"max_yaw_rate_rad_s":0.5934119456780721,"policy":"p05b-track-yaw-v1","version":1},"physics":{"body_center_offset":[5.399622023105621e-05,0.8712279796600342,-0.4413140006363392],"body_half_extents":[0.8200840055942535,0.5810779929161072,2.0059760212898254],"engine_max_torque_nm":120.80433138469988,"lateral_friction":1.0,"longitudinal_friction":1.2,"mass_kg":4691.0,"max_forward_mps":8.88896,"max_reverse_mps":2.22224,"stationary_steering_ratio":0.2,"suspension_max":0.35,"suspension_min":0.1,"track_max_brake_torque":10000,"wheel_points":[[-0.7303810119628906,0.53,-0.9612770080566406],[-0.7303810119628906,0.53,0],[-0.7303810119628906,0.53,0.9612770080566406],[0.7303810119628906,0.53,-0.9612770080566406],[0.7303810119628906,0.53,0],[0.7303810119628906,0.53,0.9612770080566406]],"wheel_radius":0.25}}
    """;
    const string Is7 = """
    {"handling":{"max_yaw_rate_rad_s":0.4886921905584123,"policy":"p05b-track-yaw-v1","version":1},"physics":{"body_center_offset":[0.0,1.0385702341794967,0.04841578006744385],"body_half_extents":[1.6451992988586426,0.5439350754022598,3.6090246438980103],"engine_max_torque_nm":2949.8732082310435,"lateral_friction":1.0,"longitudinal_friction":1.2,"mass_kg":68190.0,"max_forward_mps":16.555688000000004,"max_reverse_mps":4.1667000000000005,"stationary_steering_ratio":0.2,"suspension_max":0.35,"suspension_min":0.1,"track_max_brake_torque":75089.74730797112,"wheel_points":[[-1.30381,0.6675649869441986,-2.4024],[-1.30381,0.6675649869441986,0],[-1.30381,0.6675649869441986,2.4024],[1.30381,0.6675649869441986,-2.4024],[1.30381,0.6675649869441986,0],[1.30381,0.6675649869441986,2.4024]],"wheel_radius":0.3875649869441986}}
    """;
    public static AngularBodyBinding Select(JsonElement config)
    {
        if(config.GetProperty("version").GetInt32()!=3||config.GetProperty("profile").GetString()!="test_lab")
            throw new InvalidDataException("angular response requires source config3");
        bool Matches(string text)
        {
            using var expected=JsonDocument.Parse(text);var e=expected.RootElement;
            foreach(var p in e.GetProperty("physics").EnumerateObject())
                if(!config.TryGetProperty(p.Name,out var actual)||!SameNumeric(actual,p.Value))return false;
            var handling=config.GetProperty("handling");CheckedInput.Fields(handling,"version","policy","max_yaw_rate_rad_s");
            var want=e.GetProperty("handling");
            return handling.GetProperty("version").GetInt32()==1&&handling.GetProperty("policy").GetString()=="p05b-track-yaw-v1"
                &&SameNumeric(handling.GetProperty("max_yaw_rate_rad_s"),want.GetProperty("max_yaw_rate_rad_s"));
        }
        var half=CheckedInput.Vector(config.GetProperty("body_half_extents"),.1f,5);
        if(Matches(Ms1))return new("ms1","48f8ac675afafbe8605bd97bd92dc2c37f26673b65a548d4f0402b815f7ee9a1",4691,half,
            0x395f8781,0x390ec909,0x3919bf9b,0x3a25f4bb);
        if(Matches(Is7))return new("is7","2b72923c904678b5471ca4c8e01125f787d0baeb8cf2153c322a126fa1b6cfd7",68190,half,
            0x3776094c,0x363bac7f,0x365da392,0x3775d3e2);
        throw new InvalidDataException("angular response unsupported physical projection");
    }
    // Only the explicit IPC7 v2 qualification route can load these bindings.
    // Actual body creation still verifies every native getter bit.
    internal AngularBodyBinding(string kind,string profileHash,float massKg,Vector3 half,
        float inverseMass,Vector3 principal,Quaternion rotation)
    {
        CheckedInput.Sha256(profileHash);
        if(kind is not ("t26" or "t34" or "t3485")||!float.IsFinite(massKg)||massKg<1000||massKg>100000
            ||!float.IsFinite(inverseMass)||inverseMass<=0
            ||!float.IsFinite(principal.X)||!float.IsFinite(principal.Y)||!float.IsFinite(principal.Z)
            ||principal.X<=0||principal.Y<=0||principal.Z<=0
            ||!float.IsFinite(rotation.X)||!float.IsFinite(rotation.Y)||!float.IsFinite(rotation.Z)||!float.IsFinite(rotation.W)
            ||Math.Abs(rotation.LengthSquared()-1)>2e-5f)
            throw new InvalidDataException("stock native binding bounds");
        Kind=kind;ProfileSha256=profileHash;MassKg=massKg;HalfExtents=half;InverseMass=inverseMass;
        PrincipalInverse=principal;InertiaRotation=rotation;
    }
    static bool SameNumeric(JsonElement a,JsonElement b)
    {
        if(b.ValueKind==JsonValueKind.Number)return a.ValueKind==JsonValueKind.Number&&a.TryGetDouble(out double x)
            &&double.IsFinite(x)&&x==b.GetDouble();
        return b.ValueKind==JsonValueKind.Array&&a.ValueKind==JsonValueKind.Array&&a.GetArrayLength()==b.GetArrayLength()
            &&a.EnumerateArray().Zip(b.EnumerateArray()).All(p=>SameNumeric(p.First,p.Second));
    }
    static bool Same(float a,float b)=>BitConverter.SingleToUInt32Bits(a)==BitConverter.SingleToUInt32Bits(b);
    public void Verify(float inverseMass,Vector3 principal,Quaternion rotation)
    {
        if(!Same(inverseMass,InverseMass)||!Same(principal.X,PrincipalInverse.X)||!Same(principal.Y,PrincipalInverse.Y)
            ||!Same(principal.Z,PrincipalInverse.Z)||!Same(rotation.X,InertiaRotation.X)||!Same(rotation.Y,InertiaRotation.Y)
            ||!Same(rotation.Z,InertiaRotation.Z)||!Same(rotation.W,InertiaRotation.W))
            throw new InvalidDataException("native angular body binding mismatch");
    }
    public void Verify(Body body)
    {
        var motion=body.MotionProperties;
        Verify(motion.InverseMassUnchecked,motion.InverseInertiaDiagonal,motion.InertiaRotation);
    }
    public bool ContainsArm(Vector3 com,Vector3 point)
    {
        double x=(double)point.X-com.X,y=(double)point.Y-com.Y,z=(double)point.Z-com.Z;
        double hx=HalfExtents.X,hy=HalfExtents.Y,hz=HalfExtents.Z;
        return double.IsFinite(x)&&double.IsFinite(y)&&double.IsFinite(z)&&(x*x+y*y)+z*z<=4*((hx*hx+hy*hy)+hz*hz);
    }
    public object ToWire()=>new{inverse_mass=InverseMass,principal_inverse_diagonal=AngularMotionFrame.V(PrincipalInverse),
        inertia_rotation_xyzw=AngularMotionFrame.Q(InertiaRotation)};
}

// Immutable scalar copy; capture itself applies no new speed rejection to an
// ordinary no-contact frame. Strict frame bounds apply before it is used in a
// receipt/witness. No native handle survives this snapshot.
internal sealed record AngularMotionFrame(Vector3 Com,Quaternion Rotation,AngularContactResponse.Motion Motion,
    Matrix4x4 InverseInertia)
{
    public static AngularMotionFrame Capture(Body body,AngularBodyBinding binding)
    {
        binding.Verify(body);
        return new(body.CenterOfMassPosition,body.Rotation,new(body.GetLinearVelocity(),body.GetAngularVelocity()),body.GetInverseInertia());
    }
    public static float[] V(Vector3 v)=>[v.X,v.Y,v.Z];
    public static float[] Q(Quaternion q)=>[q.X,q.Y,q.Z,q.W];
    public static bool SameBits(Vector3 a,Vector3 b)=>BitConverter.SingleToUInt32Bits(a.X)==BitConverter.SingleToUInt32Bits(b.X)
        &&BitConverter.SingleToUInt32Bits(a.Y)==BitConverter.SingleToUInt32Bits(b.Y)&&BitConverter.SingleToUInt32Bits(a.Z)==BitConverter.SingleToUInt32Bits(b.Z);
    public float[] Tensor()=>[InverseInertia.M11,InverseInertia.M12,InverseInertia.M13,InverseInertia.M21,
        InverseInertia.M22,InverseInertia.M23,InverseInertia.M31,InverseInertia.M32,InverseInertia.M33];
    public static bool MotionInBounds(AngularContactResponse.Motion m)
    {
        var v=m.Linear;var w=m.Angular;
        double speed2=((double)v.X*v.X+(double)v.Y*v.Y)+(double)v.Z*v.Z;
        return double.IsFinite(speed2)&&speed2<=625&&float.IsFinite(w.X)&&float.IsFinite(w.Y)&&float.IsFinite(w.Z)
            &&Math.Abs((double)w.X)<=20&&Math.Abs((double)w.Y)<=20&&Math.Abs((double)w.Z)<=20;
    }
    public AngularContactResponse.Frame Validate(AngularBodyBinding binding)
    {
        var frame=new AngularContactResponse.Frame(Com,binding.InverseMass,Tensor());
        frame.VerifyBasis(Rotation,binding.PrincipalInverse,binding.InertiaRotation);
        frame.Inspect(Motion,Com,Vector3.UnitX);return frame;
    }
    public static object MotionWire(AngularContactResponse.Motion m)=>new{linear_velocity=V(m.Linear),angular_velocity=V(m.Angular)};
    public object ToWire()=>new{com=V(Com),rotation_xyzw=Q(Rotation),linear_velocity=V(Motion.Linear),
        angular_velocity=V(Motion.Angular),inverse_inertia_row_major=Tensor()};
}
