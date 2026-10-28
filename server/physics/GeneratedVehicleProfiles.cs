using System.Numerics;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using JoltPhysicsSharp;

namespace MapDrive;

// BATTLE-ANY: definitions generated from config/catalog/battle_profiles.v1.json
// (tools/battle_any_profiles.py), embedded as one resource. The physical mapping
// is the same explicit six-support test_lab projection as the WT/FV extended
// profiles; each row names its own main-wheel support rule. A qualified profile
// binds physics only; owned battle admission is decided by the server catalog.
internal static class GeneratedVehicleProfiles
{
    public const string Policy="battle-any-generated-v1";
    public const string MappingPolicy="p06t-extended-six-support-v2";
    public const int MaxDefinitionBytes=2*1024*1024;
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
                ||b.GetProperty("managed_sha256").GetString()!=ExtendedVehicleProfiles.ManagedSha
                ||b.GetProperty("native_sha256").GetString()!=ExtendedVehicleProfiles.NativeSha)
                throw new InvalidDataException("generated profile native platform/build pin");
            CheckedInput.Sha256(b.GetProperty("qualified_worker_sha256").GetString());
            var p=Bits(b.GetProperty("principal_inverse_bits"),3);var q=Bits(b.GetProperty("inertia_rotation_bits_xyzw"),4);
            return new(Kind,Hash,Mass,Half,F(b.GetProperty("inverse_mass_bits").GetUInt32()),new(F(p[0]),F(p[1]),F(p[2])),
                new(F(q[0]),F(q[1]),F(q[2]),F(q[3])));
        }
    }
    static uint[] Bits(JsonElement value,int length)
    {
        if(value.ValueKind!=JsonValueKind.Array||value.GetArrayLength()!=length)
            throw new InvalidDataException("generated binding bit array length");
        return value.EnumerateArray().Select(v=>v.GetUInt32()).ToArray();
    }
    static float F(uint value)=>BitConverter.UInt32BitsToSingle(value);
    static readonly Lazy<Dictionary<string,(JsonElement Definition,string Hash)>> Definitions=new(ReadDefinitions);
    public static bool IsGenerated(string kind)=>Definitions.Value.ContainsKey(kind);
    public static IEnumerable<string> Kinds=>Definitions.Value.Keys;
    static Dictionary<string,(JsonElement,string)> ReadDefinitions()
    {
        using var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("MapDrive.GeneratedDefinitions")
            ??throw new InvalidDataException("generated definitions absent");
        using var bytes=new MemoryStream();stream.CopyTo(bytes);
        if(bytes.Length is <1 or >MaxDefinitionBytes)throw new InvalidDataException("generated definition size");
        using var doc=CheckedInput.Json(bytes.ToArray());var r=doc.RootElement;
        CheckedInput.Fields(r,"version","profile","policy","profiles");
        if(r.GetProperty("version").GetInt32()!=1||r.GetProperty("profile").GetString()!="test_lab"
            ||r.GetProperty("policy").GetString()!=Policy)throw new InvalidDataException("generated definitions policy");
        var result=new Dictionary<string,(JsonElement,string)>();
        foreach(var row in r.GetProperty("profiles").EnumerateArray())
        {
            string kind=row.GetProperty("kind").GetString()!;
            // The five legacy and two extended labels keep their own closed loaders.
            if(kind.Length is <3 or >96||!kind.All(c=>char.IsAsciiLetterOrDigit(c)||c=='_'||c=='-')||!kind.Contains('-')
                ||kind is "wt-e100-128" or "fv215b-183")
                throw new InvalidDataException("generated definition kind");
            ValidateProjection(row);
            result.Add(kind,(row.Clone(),CheckedInput.Hash(Encoding.UTF8.GetBytes(row.GetRawText()+"\n"))));
        }
        if(result.Count is <1 or >512)throw new InvalidDataException("generated definition count");
        return result;
    }
    public static Profile Load(string root,string path,string hash)
    {
        using var doc=CheckedInput.Json(CheckedInput.FileBytes(CheckedInput.Owned(root,path),16384,hash));
        var r=doc.RootElement;
        CheckedInput.Fields(r,"version","profile","policy","kind","battle_admission","definition_sha256","definition","native_binding");
        string kind=r.GetProperty("kind").GetString()!;
        if(r.GetProperty("version").GetInt32()!=1||r.GetProperty("profile").GetString()!="test_lab"
            ||r.GetProperty("policy").GetString()!=Policy||r.GetProperty("battle_admission").ValueKind!=JsonValueKind.False
            ||!Definitions.Value.TryGetValue(kind,out var expected)||r.GetProperty("definition_sha256").GetString()!=expected.Hash
            ||!SameJson(r.GetProperty("definition"),expected.Definition)
            ||r.GetProperty("native_binding").ValueKind!=JsonValueKind.Object)
            throw new InvalidDataException("generated profile definition/source pin or admission policy");
        var result=new Profile(kind,hash,expected.Hash,expected.Definition,r.Clone());
        result.Binding();
        return result;
    }
    public static AngularBodyBinding Select(string root,JsonElement reference,JsonElement config,string kind)
    {
        CheckedInput.Fields(reference,"path","sha256");
        var p=Load(root,reference.GetProperty("path").GetString()!,reference.GetProperty("sha256").GetString()!);
        if(kind!=p.Kind||config.GetProperty("version").GetInt32()!=3||config.GetProperty("profile").GetString()!="test_lab")
            throw new InvalidDataException("generated config kind/version");
        foreach(var field in p.Physics.EnumerateObject())
            if(!config.TryGetProperty(field.Name,out var actual)||!SameJson(actual,field.Value))
                throw new InvalidDataException("generated config physical projection: "+field.Name);
        if(!SameJson(config.GetProperty("handling"),p.Definition.GetProperty("handling")))
            throw new InvalidDataException("generated config handling projection");
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
    // Same checks as ExtendedVehicleProfiles.ValidateProjection; the support
    // rule is a per-row source fact instead of a kind-name special case.
    static void ValidateProjection(JsonElement definition)
    {
        CheckedInput.Fields(definition,"kind","vehicle","source","physics","handling","mapping");
        var mapping=definition.GetProperty("mapping");
        CheckedInput.Fields(mapping,"policy","classification","historical_fidelity","support_radius","support_count","support_y_offset","motion_quality",
            "collision_steps_per_60hz");
        if(mapping.GetProperty("policy").GetString()!=MappingPolicy||mapping.GetProperty("classification").GetString()!="INFERRED_TEST_LAB_ONLY"
            ||mapping.GetProperty("historical_fidelity").ValueKind!=JsonValueKind.False||mapping.GetProperty("support_radius").GetString()!="named-equal-main-W_L0-W_R0-or-group-W_L-W_R"
            ||mapping.GetProperty("support_count").GetInt32()!=6||mapping.GetProperty("support_y_offset").GetDouble()!=.28
            ||mapping.GetProperty("motion_quality").GetString()!="Discrete"
            ||mapping.GetProperty("collision_steps_per_60hz").GetInt32()!=TrackedBodySettings.StockCollisionSteps)
            throw new InvalidDataException("generated laboratory support/motion policy");
        var p=definition.GetProperty("physics");
        CheckedInput.Fields(p,"body_half_extents","body_center_offset","wheel_points","mass_kg","max_forward_mps","max_reverse_mps",
            "engine_max_torque_nm","wheel_radius","suspension_min","suspension_max","track_max_brake_torque",
            "longitudinal_friction","lateral_friction","stationary_steering_ratio");
        var source=definition.GetProperty("source");
        CheckedInput.Fields(source,"weights_kg","speed_limits_kmh","engine_power_hp","brake_force_source","yaw_rate_degrees_s",
            "carrying_point","hull_aabb","hull_position","support_rule");
        var weights=source.GetProperty("weights_kg");CheckedInput.Fields(weights,"hull","chassis","turret","gun","engines","fueltanks","radios");
        double mass=0;
        foreach(var w in weights.EnumerateObject().OrderBy(w=>w.Name,StringComparer.Ordinal))
        {
            CheckedInput.Number(w.Value,0,100000);mass+=w.Value.GetDouble();
        }
        if(mass!=p.GetProperty("mass_kg").GetDouble())throw new InvalidDataException("generated recomputed assembly mass");
        CheckedInput.Number(p.GetProperty("mass_kg"),1000,100000);
        CheckedInput.Vector(p.GetProperty("body_half_extents"),.1f,5);
        CheckedInput.Vector(p.GetProperty("body_center_offset"),-5,5);
        var aabb=source.GetProperty("hull_aabb");CheckedInput.Fields(aabb,"min","max");
        var lo=aabb.GetProperty("min");var hi=aabb.GetProperty("max");var h=source.GetProperty("hull_position");
        CheckedInput.Vector(lo,-10,10);CheckedInput.Vector(hi,-10,10);CheckedInput.Vector(h,-5,5);
        for(int i=0;i<3;i++)
            if(hi[i].GetDouble()<=lo[i].GetDouble()||(hi[i].GetDouble()-lo[i].GetDouble())/2!=p.GetProperty("body_half_extents")[i].GetDouble()
                ||(hi[i].GetDouble()+lo[i].GetDouble())/2+h[i].GetDouble()!=p.GetProperty("body_center_offset")[i].GetDouble())
                throw new InvalidDataException("generated recomputed Hull bounds/center");
        float N(string name,float min,float max)=>CheckedInput.Number(p.GetProperty(name),min,max);
        N("max_forward_mps",1,20);N("max_reverse_mps",.5f,10);N("engine_max_torque_nm",10,10000);
        N("wheel_radius",.05f,1);N("track_max_brake_torque",100,300000);
        float min=N("suspension_min",0,1),max=N("suspension_max",.05f,1);
        if(min>=max)throw new InvalidDataException("generated suspension order");
        N("longitudinal_friction",.1f,2);N("lateral_friction",.1f,2);N("stationary_steering_ratio",0,1);
        var points=p.GetProperty("wheel_points");
        if(points.ValueKind!=JsonValueKind.Array||points.GetArrayLength()!=6)throw new InvalidDataException("six generated lab supports");
        foreach(var point in points.EnumerateArray())CheckedInput.Vector(point,-5,5);
        var carrying=source.GetProperty("carrying_point");
        if(carrying.GetArrayLength()!=2)throw new InvalidDataException("generated carrying point");
        double radius=p.GetProperty("wheel_radius").GetDouble();
        for(int i=0;i<6;i++)
            if(points[i][0].GetDouble()!=(i<3?-1:1)*carrying[0].GetDouble()||points[i][1].GetDouble()!=radius+.28
                ||points[i][2].GetDouble()!=(i%3-1)*carrying[1].GetDouble())
                throw new InvalidDataException("generated six-support source projection");
        var speed=source.GetProperty("speed_limits_kmh");
        if(speed.GetArrayLength()!=2||speed[0].GetDouble()*.27778!=p.GetProperty("max_forward_mps").GetDouble()
            ||speed[1].GetDouble()*.27778!=p.GetProperty("max_reverse_mps").GetDouble()
            ||source.GetProperty("engine_power_hp").GetDouble()*735.5/(2*Math.PI*2500/60)!=p.GetProperty("engine_max_torque_nm").GetDouble()
            ||source.GetProperty("brake_force_source").GetDouble()*9.81*radius/2!=p.GetProperty("track_max_brake_torque").GetDouble())
            throw new InvalidDataException("generated source speed/torque/brake projection");
        if(source.GetProperty("support_rule").GetString() is not ("group-W_L-W_R" or "named-W_L0-W_R0"))
            throw new InvalidDataException("generated support rule");
        var handling=definition.GetProperty("handling");CheckedInput.Fields(handling,"version","policy","max_yaw_rate_rad_s");
        if(handling.GetProperty("version").GetInt32()!=1||handling.GetProperty("policy").GetString()!="p05b-track-yaw-v1")
            throw new InvalidDataException("generated handling policy");
        CheckedInput.Number(handling.GetProperty("max_yaw_rate_rad_s"),.1f,1f);
        double expectedYaw=source.GetProperty("yaw_rate_degrees_s").GetDouble()*(Math.PI/180);
        if(Math.Abs(expectedYaw-handling.GetProperty("max_yaw_rate_rad_s").GetDouble())>1e-15)
            throw new InvalidDataException("generated source yaw projection");
    }

    // Authoring only: every embedded definition -> genuine native getter bits
    // on the pinned Windows x64 Jolt build. Writes one qualified profile per kind
    // into a fresh owned directory plus a manifest; never grants admission.
    public static int Qualify(string[] args)
    {
        if(args.Length!=5||args[0]!="--qualify-generated-profiles"||args[1]!="--local-root"||args[3]!="--out")
            throw new InvalidDataException("expected --qualify-generated-profiles --local-root R --out DIR");
        string root=Path.GetFullPath(args[2]),outDir=Path.GetFullPath(args[4]);
        if(!outDir.StartsWith(root.TrimEnd(Path.DirectorySeparatorChar)+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)
            ||Directory.Exists(outDir)||File.Exists(outDir)||!Directory.Exists(Path.GetDirectoryName(outDir)))
            throw new InvalidDataException("fresh output directory below local root required");
        for(string? item=root;item!=null;item=Path.GetDirectoryName(item))
            if((File.GetAttributes(item)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("local root reparse point");
        var runtime=ExtendedProfileQualification.Runtime();
        if(!Foundation.Init(false))throw new InvalidOperationException("Jolt initialization failed");
        var rows=new List<object>();
        Directory.CreateDirectory(outDir);
        try
        {
            foreach(var kind in Definitions.Value.Keys.OrderBy(k=>k,StringComparer.Ordinal))
            {
                var (definition,hash)=Definitions.Value[kind];
                var p=new Profile(kind,new string('0',64),hash,definition,definition);
                var native=Native(p,runtime);
                var document=new JsonObject{["version"]=1,["profile"]="test_lab",["policy"]=Policy,["kind"]=kind,
                    ["battle_admission"]=false,["definition_sha256"]=hash,["definition"]=JsonNode.Parse(definition.GetRawText()),
                    ["native_binding"]=JsonSerializer.SerializeToNode(native)};
                byte[] bytes=Encoding.UTF8.GetBytes(document.ToJsonString()+"\n");
                if(bytes.Length>16384)throw new InvalidDataException("generated qualified profile bound");
                string name=kind+"-qualified-profile.json";
                using(var file=new FileStream(Path.Combine(outDir,name),FileMode.CreateNew))file.Write(bytes);
                rows.Add(new{kind,file=name,bytes=bytes.Length,sha256=CheckedInput.Hash(bytes),definition_sha256=hash,native_binding=native});
            }
        }
        finally { Foundation.Shutdown(); }
        byte[] manifest=JsonSerializer.SerializeToUtf8Bytes(new{version=1,@event="generated_profiles_qualified",policy=Policy,
            classification="OBSERVED_PINNED_WINDOWS_X64_TEST_LAB_ONLY",runtime,battle_admission=false,owner_acceptance="NOT_RUN",profiles=rows});
        using(var file=new FileStream(Path.Combine(outDir,"qualified-manifest.json"),FileMode.CreateNew))file.Write(manifest);
        Console.WriteLine(JsonSerializer.Serialize(new{status="PASS_GENERATED_QUALIFIED",profiles=rows.Count,out_dir=outDir}));
        return 0;
    }
    static uint B(float value)=>BitConverter.SingleToUInt32Bits(value);
    static object Native(Profile profile,ExtendedProfileQualification.RuntimePins runtime)
    {
        using var pairs=new ObjectLayerPairFilterTable(2);pairs.EnableCollision(0,1);pairs.EnableCollision(1,1);
        using var broad=new BroadPhaseLayerInterfaceTable(2,2);broad.MapObjectToBroadPhaseLayer(0,0);broad.MapObjectToBroadPhaseLayer(1,1);
        using var filter=new ObjectVsBroadPhaseLayerFilterTable(broad,2,pairs,2);
        using var world=new PhysicsSystem(new PhysicsSystemSettings { MaxBodies=16,MaxBodyPairs=64,MaxContactConstraints=64,
            ObjectLayerPairFilter=pairs,BroadPhaseLayerInterface=broad,ObjectVsBroadPhaseLayerFilter=filter });
        using var shape=new BoxShape(profile.Half);
        AngularBodyBinding? binding=null;object? native=null;
        foreach(float yaw in new float[]{0,.7f,-2.4f})
        {
            var rotation=Quaternion.CreateFromAxisAngle(Vector3.UnitY,yaw);
            using var settings=TrackedBodySettings.Create(shape,profile.Mass,Vector3.Transform(profile.Center,rotation),rotation);
            var body=world.BodyInterface.CreateBody(settings);
            try
            {
                var m=body.MotionProperties;
                float inverse=m.InverseMassUnchecked;var principal=m.InverseInertiaDiagonal;var q=m.InertiaRotation;
                binding??=new(profile.Kind,profile.DefinitionHash,profile.Mass,profile.Half,inverse,principal,q);
                // Exact getter bits must stay the same at each actual body yaw.
                binding.Verify(body);
                var frame=AngularMotionFrame.Capture(body,binding);frame.Validate(binding);
                if(yaw==0)VerifyAnalyticBox(frame.InverseInertia,profile.Mass,profile.Half,inverse);
                native??=new { version=1,runtime.platform,runtime.jolt_physics_sharp,runtime.managed_sha256,runtime.native_sha256,
                    runtime.qualified_worker_sha256,inverse_mass_bits=B(inverse),principal_inverse_bits=new uint[]{B(principal.X),B(principal.Y),B(principal.Z)},
                    inertia_rotation_bits_xyzw=new uint[]{B(q.X),B(q.Y),B(q.Z),B(q.W)} };
            }
            finally { world.BodyInterface.DestroyBody(body.ID); }
        }
        return native!;
    }
    static void VerifyAnalyticBox(Matrix4x4 tensor,float mass,Vector3 half,float inverseMass)
    {
        void Close(double actual,double expected)
        {
            if(!double.IsFinite(actual)||Math.Abs(actual-expected)>Math.Max(1e-10,Math.Abs(expected)*2e-5))
                throw new InvalidDataException("generated actual inertia disagrees with independent box tensor");
        }
        Close(inverseMass,1.0/mass);
        Close(tensor.M11,3.0/(mass*((double)half.Y*half.Y+(double)half.Z*half.Z)));
        Close(tensor.M22,3.0/(mass*((double)half.X*half.X+(double)half.Z*half.Z)));
        Close(tensor.M33,3.0/(mass*((double)half.X*half.X+(double)half.Y*half.Y)));
        foreach(float off in new[]{tensor.M12,tensor.M13,tensor.M21,tensor.M23,tensor.M31,tensor.M32})Close(off,0);
    }
}
