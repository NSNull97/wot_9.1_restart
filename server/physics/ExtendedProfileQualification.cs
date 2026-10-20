using System.IO.Compression;
using System.Numerics;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text.Json.Nodes;
using JoltPhysicsSharp;

namespace MapDrive;

// Authoring only: actual source bytes -> fixed projection -> genuine native
// getter bits and independent box/basis checks. No battle admission is granted.
internal static class ExtendedProfileQualification
{
    public sealed record RuntimePins(string platform,string jolt_physics_sharp,string managed_sha256,
        string native_sha256,string qualified_worker_sha256);
    public static RuntimePins Runtime()
    {
        if(!OperatingSystem.IsWindows()||RuntimeInformation.ProcessArchitecture!=Architecture.X64)
            throw new InvalidDataException("extended qualification pinned to Windows x64");
        string worker=Assembly.GetExecutingAssembly().Location,managed=typeof(Body).Assembly.Location;
        string native=Path.Combine(Path.GetDirectoryName(worker)!,"runtimes","win-x64","native","joltc.dll");
        string managedHash=FileHash(managed),nativeHash=FileHash(native);
        if(managedHash!=ExtendedVehicleProfiles.ManagedSha||nativeHash!=ExtendedVehicleProfiles.NativeSha)
            throw new InvalidDataException("extended qualification Jolt dependency pin");
        return new("windows-x64","2.22.0",managedHash,nativeHash,FileHash(worker));
    }
    static string FileHash(string path)
    {
        for(string? item=Path.GetFullPath(path);item!=null;item=Path.GetDirectoryName(item))
            if((File.GetAttributes(item)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("qualification dependency reparse point");
        using var stream=File.OpenRead(path);
        if(stream.Length is <1 or >32*1024*1024)throw new InvalidDataException("qualification dependency file bound");
        return Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(stream));
    }
    public static int Run(string[] args)
    {
        if(args.Length!=8||args[0]!="--qualify-extended-profile"||args[2]!="--profile-sha256"||args[4]!="--local-root"||args[6]!="--source-root")
            throw new InvalidDataException("expected pinned extended draft/local-root/source-root");
        var profile=ExtendedVehicleProfiles.Load(Path.GetFullPath(args[5]),args[1],args[3],false);
        VerifySources(Path.GetFullPath(args[7]),profile.Definition.GetProperty("source"));
        var runtime=Runtime();
        if(!Foundation.Init(false))throw new InvalidOperationException("Jolt initialization failed");
        try { Qualify(profile,runtime); }
        finally { Foundation.Shutdown(); }
        return 0;
    }
    static void VerifySources(string root,JsonElement source)
    {
        var files=source.GetProperty("files");
        if(files.ValueKind!=JsonValueKind.Array||files.GetArrayLength()!=7)throw new InvalidDataException("extended source file count");
        foreach(var f in files.EnumerateArray())
        {
            CheckedInput.Fields(f,"path","bytes","sha256");
            int length=f.GetProperty("bytes").GetInt32();
            if(length is <1 or >1024*1024)throw new InvalidDataException("extended source file size");
            var bytes=CheckedInput.FileBytes(CheckedInput.Owned(root,f.GetProperty("path").GetString()!),1024*1024,f.GetProperty("sha256").GetString());
            if(bytes.Length!=length)throw new InvalidDataException("extended source exact file length");
        }
        var p=source.GetProperty("package");
        string path=CheckedInput.Owned(root,p.GetProperty("path").GetString()!);
        using var package=File.OpenRead(path);
        if(package.Length!=p.GetProperty("bytes").GetInt64())throw new InvalidDataException("extended package size");
        // The prior full-package hash is retained provenance, not a claim that
        // this bounded qualifier rehashed a1.18GB package. The exact selected
        // member is rehashed now, and never exported or executed.
        var member=source.GetProperty("hull_member");CheckedInput.Fields(member,"path","bytes","sha256");
        int memberBytes=member.GetProperty("bytes").GetInt32();
        if(memberBytes is <1 or >65536)throw new InvalidDataException("extended Hull member bound");
        using var archive=new ZipArchive(package,ZipArchiveMode.Read);
        string name=member.GetProperty("path").GetString()!;
        var matches=archive.Entries.Where(e=>e.FullName==name).ToArray();
        if(matches.Length!=1||matches[0].Length!=memberBytes)throw new InvalidDataException("extended exact Hull member identity");
        using var input=matches[0].Open();var raw=new byte[memberBytes];input.ReadExactly(raw);
        if(input.ReadByte()!=-1||CheckedInput.Hash(raw)!=member.GetProperty("sha256").GetString())
            throw new InvalidDataException("extended Hull member SHA256");
    }
    static uint B(float value)=>BitConverter.SingleToUInt32Bits(value);
    static void Qualify(ExtendedVehicleProfiles.Profile profile,RuntimePins runtime)
    {
        using var pairs=new ObjectLayerPairFilterTable(2);pairs.EnableCollision(0,1);pairs.EnableCollision(1,1);
        using var broad=new BroadPhaseLayerInterfaceTable(2,2);broad.MapObjectToBroadPhaseLayer(0,0);broad.MapObjectToBroadPhaseLayer(1,1);
        using var filter=new ObjectVsBroadPhaseLayerFilterTable(broad,2,pairs,2);
        using var world=new PhysicsSystem(new PhysicsSystemSettings { MaxBodies=16,MaxBodyPairs=64,MaxContactConstraints=64,
            ObjectLayerPairFilter=pairs,BroadPhaseLayerInterface=broad,ObjectVsBroadPhaseLayerFilter=filter });
        using var shape=new BoxShape(profile.Half);
        AngularBodyBinding? binding=null;object? nativeBinding=null;
        var frames=new List<object>();
        foreach(float yaw in new float[]{0,.7f,-2.4f})
        {
            var rotation=Quaternion.CreateFromAxisAngle(Vector3.UnitY,yaw);
            using var settings=TrackedBodySettings.Create(shape,profile.Mass,Vector3.Transform(profile.Center,rotation),rotation);
            var body=world.BodyInterface.CreateBody(settings);
            try
            {
                var m=body.MotionProperties;
                float inverse=m.InverseMassUnchecked;var principal=m.InverseInertiaDiagonal;var q=m.InertiaRotation;
                binding??=new(profile.Kind,profile.Hash,profile.Mass,profile.Half,inverse,principal,q);
                // Exact getter bits must stay the same at each actual body yaw.
                binding.Verify(body);
                var frame=AngularMotionFrame.Capture(body,binding);frame.Validate(binding);
                if(yaw==0)VerifyAnalyticBox(frame.InverseInertia,profile.Mass,profile.Half,inverse);
                frames.Add(new{yaw,frame=frame.ToWire(),binding=binding.ToWire()});
                nativeBinding??=new { version=1,runtime.platform,runtime.jolt_physics_sharp,runtime.managed_sha256,runtime.native_sha256,
                    runtime.qualified_worker_sha256,inverse_mass_bits=B(inverse),principal_inverse_bits=new uint[]{B(principal.X),B(principal.Y),B(principal.Z)},
                    inertia_rotation_bits_xyzw=new uint[]{B(q.X),B(q.Y),B(q.Z),B(q.W)} };
            }
            finally { world.BodyInterface.DestroyBody(body.ID); }
        }
        var qualified=JsonNode.Parse(profile.Document.GetRawText())!.AsObject();
        qualified["native_binding"]=JsonSerializer.SerializeToNode(nativeBinding);
        byte[] output=JsonSerializer.SerializeToUtf8Bytes(new { version=2,@event="extended_profile_qualified",kind=profile.Kind,
            classification="OBSERVED_PINNED_WINDOWS_X64_TEST_LAB_ONLY",source_draft_sha256=profile.Hash,definition_sha256=profile.DefinitionHash,
            battle_admission=false,owner_acceptance="NOT_RUN",runtime,qualified_profile=qualified,basis_frames=frames });
        if(output.Length>32768)throw new InvalidDataException("extended qualification output bound");
        Console.OpenStandardOutput().Write(output);Console.WriteLine();
    }
    static void VerifyAnalyticBox(Matrix4x4 tensor,float mass,Vector3 half,float inverseMass)
    {
        void Close(double actual,double expected)
        {
            if(!double.IsFinite(actual)||Math.Abs(actual-expected)>Math.Max(1e-10,Math.Abs(expected)*2e-5))
                throw new InvalidDataException("extended actual inertia disagrees with independent box tensor");
        }
        Close(inverseMass,1.0/mass);
        Close(tensor.M11,3.0/(mass*((double)half.Y*half.Y+(double)half.Z*half.Z)));
        Close(tensor.M22,3.0/(mass*((double)half.X*half.X+(double)half.Z*half.Z)));
        Close(tensor.M33,3.0/(mass*((double)half.X*half.X+(double)half.Y*half.Y)));
        foreach(float off in new[]{tensor.M12,tensor.M13,tensor.M21,tensor.M23,tensor.M31,tensor.M32})Close(off,0);
    }
}
