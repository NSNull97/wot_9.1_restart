using System.Numerics;
using System.Reflection;
using System.Text;
using System.Text.Json;

namespace MapDrive;

// Closed source definitions, explicitly approximate six-support test_lab mapping.
// A private source_profile pin qualifies physics only; it never enables owned
// vehicle admission. No mass-based kind lookup or fallback to an old profile.
internal static class StockVehicleProfiles
{
    public const string Policy="p04m-stock-six-support-v1";
    public const string ManagedSha="b4a700ac859c9304a7217e2ea499dec6e2b280dcad2ee02e910c4cc909f0ba67";
    public const string NativeSha="79125ab6882a1aeeecd5509bfe9edf383e8e48a34d9a8b642a6b9a197d44df74";
    public sealed record Profile(string Kind,string Hash,string DefinitionHash,JsonElement Definition,JsonElement Document)
    {
        public JsonElement Physics=>Definition.GetProperty("physics");
        public float Mass=>CheckedInput.Number(Physics.GetProperty("mass_kg"),1000,100000);
        public Vector3 Half=>CheckedInput.Vector(Physics.GetProperty("body_half_extents"),.1f,5);
        public Vector3 Center=>CheckedInput.Vector(Physics.GetProperty("body_center_offset"),-5,5);
        public AngularBodyBinding Binding()
        {
            var b=Document.GetProperty("native_binding");
            CheckedInput.Fields(b,"version","platform","jolt_physics_sharp","managed_sha256","native_sha256",
                "qualified_worker_sha256","inverse_mass_bits","principal_inverse_bits","inertia_rotation_bits_xyzw");
            if(b.GetProperty("version").GetInt32()!=1||b.GetProperty("platform").GetString()!="windows-x64"
                ||b.GetProperty("jolt_physics_sharp").GetString()!="2.22.0"
                ||b.GetProperty("managed_sha256").GetString()!=ManagedSha||b.GetProperty("native_sha256").GetString()!=NativeSha)
                throw new InvalidDataException("stock profile native platform/build pin");
            CheckedInput.Sha256(b.GetProperty("qualified_worker_sha256").GetString());
            var p=Bits(b.GetProperty("principal_inverse_bits"),3);var q=Bits(b.GetProperty("inertia_rotation_bits_xyzw"),4);
            return new(Kind,Hash,Mass,Half,F(b.GetProperty("inverse_mass_bits").GetUInt32()),new(F(p[0]),F(p[1]),F(p[2])),
                new(F(q[0]),F(q[1]),F(q[2]),F(q[3])));
        }
    }
    static uint[] Bits(JsonElement value,int length)
    {
        if(value.ValueKind!=JsonValueKind.Array||value.GetArrayLength()!=length)
            throw new InvalidDataException("stock binding bit array length");
        return value.EnumerateArray().Select(v=>v.GetUInt32()).ToArray();
    }
    static float F(uint value)=>BitConverter.UInt32BitsToSingle(value);
    static readonly Dictionary<string,(JsonElement Definition,string Hash)> Definitions=ReadDefinitions();
    static Dictionary<string,(JsonElement,string)> ReadDefinitions()
    {
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("MapDrive.StockDefinitions")
            ??throw new InvalidDataException("stock definitions absent");
        using var bytes=new MemoryStream();stream.CopyTo(bytes);
        if(bytes.Length is <1 or >32768)throw new InvalidDataException("stock definition size");
        using var doc=CheckedInput.Json(bytes.ToArray());var r=doc.RootElement;
        CheckedInput.Fields(r,"version","profile","policy","profiles");
        if(r.GetProperty("version").GetInt32()!=1||r.GetProperty("profile").GetString()!="test_lab"
            ||r.GetProperty("policy").GetString()!=Policy)throw new InvalidDataException("stock definitions policy");
        var result=new Dictionary<string,(JsonElement,string)>();
        foreach(var row in r.GetProperty("profiles").EnumerateArray())
        {
            string kind=row.GetProperty("kind").GetString()!;
            if(kind is not ("t26" or "t34" or "t3485"))throw new InvalidDataException("stock definition kind");
            ValidateProjection(row);
            result.Add(kind,(row.Clone(),CheckedInput.Hash(Encoding.UTF8.GetBytes(row.GetRawText()+"\n"))));
        }
        if(result.Count!=3)throw new InvalidDataException("three stock definitions required");
        return result;
    }
    public static Profile Load(string root,string path,string hash,bool qualified)
    {
        using var doc=CheckedInput.Json(CheckedInput.FileBytes(CheckedInput.Owned(root,path),16384,hash));
        var r=doc.RootElement;
        CheckedInput.Fields(r,"version","profile","policy","kind","battle_admission","definition_sha256","definition","native_binding");
        string kind=r.GetProperty("kind").GetString()!;
        if(r.GetProperty("version").GetInt32()!=1||r.GetProperty("profile").GetString()!="test_lab"
            ||r.GetProperty("policy").GetString()!=Policy||r.GetProperty("battle_admission").ValueKind!=JsonValueKind.False
            ||!Definitions.TryGetValue(kind,out var expected)||r.GetProperty("definition_sha256").GetString()!=expected.Hash
            ||!SameJson(r.GetProperty("definition"),expected.Definition))
            throw new InvalidDataException("stock profile definition/source pin or admission policy");
        if(qualified?r.GetProperty("native_binding").ValueKind!=JsonValueKind.Object:r.GetProperty("native_binding").ValueKind!=JsonValueKind.Null)
            throw new InvalidDataException(qualified?"stock native binding qualification absent":"qualification requires unbound source draft");
        var result=new Profile(kind,hash,expected.Hash,expected.Definition,r.Clone());
        if(qualified)result.Binding();
        return result;
    }
    public static AngularBodyBinding Select(string root,JsonElement reference,JsonElement config,string kind)
    {
        CheckedInput.Fields(reference,"path","sha256");
        var p=Load(root,reference.GetProperty("path").GetString()!,reference.GetProperty("sha256").GetString()!,true);
        if(kind!=p.Kind||config.GetProperty("version").GetInt32()!=3||config.GetProperty("profile").GetString()!="test_lab")
            throw new InvalidDataException("stock config kind/version");
        foreach(var field in p.Physics.EnumerateObject())
            if(!config.TryGetProperty(field.Name,out var actual)||!SameJson(actual,field.Value))
                throw new InvalidDataException("stock config physical projection: "+field.Name);
        if(!SameJson(config.GetProperty("handling"),p.Definition.GetProperty("handling")))
            throw new InvalidDataException("stock config handling projection");
        return p.Binding();
    }
    static bool SameJson(JsonElement a,JsonElement b)
    {
        if(a.ValueKind!=b.ValueKind)return false;
        switch(b.ValueKind)
        {
            case JsonValueKind.Number:return a.TryGetDouble(out double x)&&double.IsFinite(x)&&x==b.GetDouble();
            case JsonValueKind.String:return a.GetString()==b.GetString();
            case JsonValueKind.True:case JsonValueKind.False:case JsonValueKind.Null:return true;
            case JsonValueKind.Array:return a.GetArrayLength()==b.GetArrayLength()&&a.EnumerateArray().Zip(b.EnumerateArray()).All(p=>SameJson(p.First,p.Second));
            case JsonValueKind.Object:
                var fields=b.EnumerateObject().Select(p=>p.Name).ToArray();
                CheckedInput.Fields(a,fields);
                return fields.All(name=>SameJson(a.GetProperty(name),b.GetProperty(name)));
            default:return false;
        }
    }
    static void ValidateProjection(JsonElement definition)
    {
        CheckedInput.Fields(definition,"kind","vehicle","source","physics","handling","mapping");
        var mapping=definition.GetProperty("mapping");
        CheckedInput.Fields(mapping,"policy","classification","historical_fidelity","support_radius","support_count","support_y_offset","motion_quality",
            "collision_steps_per_60hz");
        if(mapping.GetProperty("policy").GetString()!=Policy||mapping.GetProperty("classification").GetString()!="INFERRED_TEST_LAB_ONLY"
            ||mapping.GetProperty("historical_fidelity").ValueKind!=JsonValueKind.False||mapping.GetProperty("support_radius").GetString()!="equal-main-W_L-W_R"
            ||mapping.GetProperty("support_count").GetInt32()!=6||mapping.GetProperty("support_y_offset").GetDouble()!=.28
            ||mapping.GetProperty("motion_quality").GetString()!="Discrete"
            ||mapping.GetProperty("collision_steps_per_60hz").GetInt32()!=TrackedBodySettings.StockCollisionSteps)
            throw new InvalidDataException("stock laboratory support/motion policy");
        var p=definition.GetProperty("physics");
        CheckedInput.Fields(p,"body_half_extents","body_center_offset","wheel_points","mass_kg","max_forward_mps","max_reverse_mps",
            "engine_max_torque_nm","wheel_radius","suspension_min","suspension_max","track_max_brake_torque",
            "longitudinal_friction","lateral_friction","stationary_steering_ratio");
        var source=definition.GetProperty("source");
        var weights=source.GetProperty("weights_kg");CheckedInput.Fields(weights,"hull","chassis","turret","gun","engines","fueltanks","radios");
        double mass=weights.EnumerateObject().Sum(w=>(double)CheckedInput.Number(w.Value,1,100000));
        if(mass!=p.GetProperty("mass_kg").GetDouble())throw new InvalidDataException("stock recomputed assembly mass");
        CheckedInput.Number(p.GetProperty("mass_kg"),1000,100000);
        CheckedInput.Vector(p.GetProperty("body_half_extents"),.1f,5);
        CheckedInput.Vector(p.GetProperty("body_center_offset"),-5,5);
        var aabb=source.GetProperty("hull_aabb");CheckedInput.Fields(aabb,"min","max");
        var lo=aabb.GetProperty("min");var hi=aabb.GetProperty("max");var h=source.GetProperty("hull_position");
        CheckedInput.Vector(lo,-10,10);CheckedInput.Vector(hi,-10,10);CheckedInput.Vector(h,-5,5);
        for(int i=0;i<3;i++)
            if(hi[i].GetDouble()<=lo[i].GetDouble()||(hi[i].GetDouble()-lo[i].GetDouble())/2!=p.GetProperty("body_half_extents")[i].GetDouble()
                ||(hi[i].GetDouble()+lo[i].GetDouble())/2+h[i].GetDouble()!=p.GetProperty("body_center_offset")[i].GetDouble())
                throw new InvalidDataException("stock recomputed Hull bounds/center");
        float N(string name,float min,float max)=>CheckedInput.Number(p.GetProperty(name),min,max);
        N("max_forward_mps",1,20);N("max_reverse_mps",.5f,10);N("engine_max_torque_nm",10,10000);
        N("wheel_radius",.05f,1);N("track_max_brake_torque",100,100000);
        float min=N("suspension_min",0,1),max=N("suspension_max",.05f,1);
        if(min>=max)throw new InvalidDataException("stock suspension order");
        N("longitudinal_friction",.1f,2);N("lateral_friction",.1f,2);N("stationary_steering_ratio",0,1);
        var points=p.GetProperty("wheel_points");
        if(points.ValueKind!=JsonValueKind.Array||points.GetArrayLength()!=6)throw new InvalidDataException("six stock lab supports");
        foreach(var point in points.EnumerateArray())CheckedInput.Vector(point,-5,5);
        var carrying=source.GetProperty("carrying_point");
        if(carrying.GetArrayLength()!=2)throw new InvalidDataException("stock carrying point");
        double radius=p.GetProperty("wheel_radius").GetDouble();
        for(int i=0;i<6;i++)
            if(points[i][0].GetDouble()!=(i<3?-1:1)*carrying[0].GetDouble()||points[i][1].GetDouble()!=radius+.28
                ||points[i][2].GetDouble()!=(i%3-1)*carrying[1].GetDouble())
                throw new InvalidDataException("stock six-support source projection");
        var speed=source.GetProperty("speed_limits_kmh");
        if(speed.GetArrayLength()!=2||speed[0].GetDouble()*.27778!=p.GetProperty("max_forward_mps").GetDouble()
            ||speed[1].GetDouble()*.27778!=p.GetProperty("max_reverse_mps").GetDouble()
            ||source.GetProperty("engine_power_hp").GetDouble()*735.5/(2*Math.PI*2500/60)!=p.GetProperty("engine_max_torque_nm").GetDouble()
            ||source.GetProperty("brake_force_source").GetDouble()*9.81*radius/2!=p.GetProperty("track_max_brake_torque").GetDouble())
            throw new InvalidDataException("stock source speed/torque/brake projection");
        var groups=source.GetProperty("wheel_groups");
        if(groups.GetArrayLength()<2||groups[0].GetProperty("template").GetString()!="W_L"||groups[1].GetProperty("template").GetString()!="W_R"
            ||groups[0].GetProperty("radius").GetDouble()!=p.GetProperty("wheel_radius").GetDouble()
            ||groups[1].GetProperty("radius").GetDouble()!=p.GetProperty("wheel_radius").GetDouble())
            throw new InvalidDataException("stock main W_L/W_R radius policy");
        var handling=definition.GetProperty("handling");CheckedInput.Fields(handling,"version","policy","max_yaw_rate_rad_s");
        if(handling.GetProperty("version").GetInt32()!=1||handling.GetProperty("policy").GetString()!="p05b-track-yaw-v1")
            throw new InvalidDataException("stock handling policy");
        CheckedInput.Number(handling.GetProperty("max_yaw_rate_rad_s"),.1f,1.5f);
        double expectedYaw=source.GetProperty("yaw_rate_degrees_s").GetDouble()*(Math.PI/180);
        if(Math.Abs(expectedYaw-handling.GetProperty("max_yaw_rate_rad_s").GetDouble())>1e-15)
            throw new InvalidDataException("stock source yaw projection");
    }
}
