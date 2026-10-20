using System.Text.Json;
using JoltPhysicsSharp;
using MapDrive;

internal static class DraftReversalChecks
{
    static void Need(bool value,string code){if(!value)throw new InvalidDataException(code);}
    public static int Main(string[] args)
    {
        bool initialized=false;string? output=null;
        try
        {
            Need(args.Length==10,"--local-root ROOT --manifest PATH --manifest-sha256 SHA --mode unit|physical|all --out FRESH");
            var options=new Dictionary<string,string>();for(int i=0;i<args.Length;i+=2)Need(options.TryAdd(args[i],args[i+1]),"duplicate option");
            Need(options.Keys.Order().SequenceEqual(new[]{"--local-root","--manifest","--manifest-sha256","--mode","--out"}),"exact options");
            string mode=options["--mode"];Need(mode is "unit"or"physical"or"all","closed mode");
            string root=Path.GetFullPath(options["--local-root"]);output=Path.GetFullPath(options["--out"]);
            CheckedInput.Owned(root,Path.GetDirectoryName(output)!);Need(!Directory.Exists(output)&&!File.Exists(output),"fresh output required");
            var manifest=BattleSceneInput.Load(root,options["--manifest"],options["--manifest-sha256"]);
            Directory.CreateDirectory(output);Need(Foundation.Init(false),"native Jolt init");initialized=true;
            object? unit=mode is "unit"or"all"?DriverLogicUnits.Run(manifest):null;
            if(unit!=null)
            {using var unitFile=new FileStream(Path.Combine(output,"unit-result.json"),FileMode.CreateNew);JsonSerializer.Serialize(unitFile,unit,new JsonSerializerOptions{WriteIndented=true});}
            object? physical=mode is "physical"or"all"?MovingReverseChecks.RunAll(manifest,output):null;
            using var stream=new FileStream(Path.Combine(output,"result.json"),FileMode.CreateNew,FileAccess.Write,FileShare.Read);
            JsonSerializer.Serialize(stream,new{schema="p05c-intent-reversal-component.v1",status="PASS",manifest_sha256=manifest.Hash,
                mode,unit,physical,native_client="NOT_RUN",historical_physics=false},new JsonSerializerOptions{WriteIndented=true});return 0;
        }
        catch(Exception ex)
        {
            Console.Error.WriteLine(ex);
            if(output!=null&&Directory.Exists(output))
            {using var failure=new FileStream(Path.Combine(output,"failure.json"),FileMode.CreateNew);JsonSerializer.Serialize(failure,new{status="FAIL_RETAINED",type=ex.GetType().Name,reason=ex.Message});}
            return 1;
        }
        finally{if(initialized)Foundation.Shutdown();}
    }
}
