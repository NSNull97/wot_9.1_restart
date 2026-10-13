using System.Numerics;

namespace MapDrive;

// Catalog8 only. Old catalog5/6/7 decisions/debits stay in FractureResponse.
// One immutable PRE and one remaining (v,omega) pair supply every mode; query
// evaluation is read-only. Only an actual hull callback can call TryAdmit.
internal sealed class AngularFractureResponse
{
    const int Limit=FractureResponse.MaxFractures;
    public sealed record Contact(Vector3 Point,Vector3 Normal);
    public sealed record Receipt(uint ObjectId,int Substep,int Order,Vector3 Point,Vector3 Normal,Vector3 Velocity,
        string Mode,AngularContactResponse.Motion BudgetAfter,AngularContactResponse.Motion SolverAfter,
        Contact? LegacyLinearCandidate,string? SolverBranch)
    {
        public object ToWire()
        {
            var v=AngularMotionFrame.V;
            if(Mode=="angular_corner")
            {
                if(LegacyLinearCandidate==null||SolverBranch is not("applied" or "noop_nonclosing" or "noop_quantized"))
                    throw new InvalidDataException("uncompleted angular receipt");
                return new{object_id=ObjectId,substep=Substep,order=Order,point=v(Point),normal=v(Normal),mode=Mode,
                    budget_after=AngularMotionFrame.MotionWire(BudgetAfter),solver_after=AngularMotionFrame.MotionWire(SolverAfter),
                    energy_j=FractureResponse.EnergyJ,legacy_linear_candidate=new{point=v(LegacyLinearCandidate.Point),normal=v(LegacyLinearCandidate.Normal)},
                    solver_branch=SolverBranch};
            }
            if(Mode is not("normal_linear" or "total_linear")||LegacyLinearCandidate!=null||SolverBranch!=null)
                throw new InvalidDataException("invalid linear receipt mode");
            return new{object_id=ObjectId,substep=Substep,order=Order,point=v(Point),normal=v(Normal),mode=Mode,
                budget_after=AngularMotionFrame.MotionWire(BudgetAfter),solver_after=AngularMotionFrame.MotionWire(SolverAfter),energy_j=FractureResponse.EnergyJ};
        }
    }
    public sealed record Witness(int Substep,AngularMotionFrame Pre,AngularMotionFrame PostSolver)
    {
        public object ToWire()=>new{substep=Substep,pre=Pre.ToWire(),post_solver=PostSolver.ToWire()};
    }
    sealed record Candidate(Contact Contact,double Score,AngularContactResponse.Motion Output);
    readonly int ownerThread=Environment.CurrentManagedThreadId;
    readonly float mass;
    readonly AngularBodyBinding binding;
    readonly Dictionary<uint,bool> eligible; // true: fence with angular fallback
    readonly Dictionary<uint,bool> decisions=new();
    readonly HashSet<uint> admitted=new();
    readonly List<Receipt> receipts=new();
    readonly List<Witness> witnesses=new();
    int fault,step;uint pairObject;
    AngularMotionFrame? pre;
    AngularContactResponse.Frame? preKernel;
    AngularContactResponse.Motion remaining;
    Candidate? angularCandidate;
    public IReadOnlyList<Receipt> Receipts=>receipts;
    public IReadOnlyList<Witness> Witnesses=>witnesses;
    public AngularFractureResponse(float massKg,CheckedInput.CatalogSpec catalog,AngularBodyBinding bodyBinding)
    {
        if(catalog.Version!=8||!catalog.Fractures||!float.IsFinite(massKg)||massKg!=bodyBinding.MassKg)
            throw new InvalidDataException("angular fracture profile mismatch");
        mass=massKg;binding=bodyBinding;
        eligible=new();
        foreach(var e in catalog.Entries)
        {
            if(e.RamEnergyJ!=8000||e.RamResponse is not("normal_linear" or "total_linear_angular_fallback")
                ||(e.RamResponse=="total_linear_angular_fallback"&&e.Kind!="fragile"))
                throw new InvalidDataException("angular fracture catalog mode mismatch");
            eligible.Add(e.ObjectId,e.RamResponse=="total_linear_angular_fallback");
        }
    }
    // Bounded reason codes, no allocation/logging or throwing in callbacks.
    // 1 thread; 2 contact; 3 count; 4 kernel/frame; 5 pair ordering/query.
    public void CallbackFault(int reason)=>Interlocked.CompareExchange(ref fault,reason,0);
    public void CallbackThreadCheck(){if(Environment.CurrentManagedThreadId!=ownerThread)CallbackFault(1);}
    public void Check()
    {
        if(Environment.CurrentManagedThreadId!=ownerThread||Volatile.Read(ref fault)!=0)
            throw new InvalidOperationException("angular fracture callback invariant "+Volatile.Read(ref fault));
    }
    bool CallbackReady(){CallbackThreadCheck();return Volatile.Read(ref fault)==0;}
    public void BeginAdvance(){Check();decisions.Clear();admitted.Clear();receipts.Clear();witnesses.Clear();pre=null;preKernel=null;}
    public void BeginSubstep(int substep,AngularMotionFrame frame)
    {
        Check();
        if(substep<1||substep>6||!Bounded(frame.Motion.Linear,256))throw new InvalidDataException("angular PRE substep/velocity");
        step=substep;pre=frame;preKernel=null;remaining=frame.Motion;decisions.Clear();angularCandidate=null;pairObject=0;
    }
    public bool NeedsPrepass(uint objectId)=>Environment.CurrentManagedThreadId==ownerThread&&Volatile.Read(ref fault)==0
        &&decisions.Count<Limit&&eligible.ContainsKey(objectId)&&!admitted.Contains(objectId)&&!decisions.ContainsKey(objectId);
    public void BeginPair(uint objectId)
    {
        if(!CallbackReady())return;
        if(!NeedsPrepass(objectId)||pre==null){CallbackFault(5);return;}
        pairObject=objectId;angularCandidate=null;
    }
    AngularContactResponse.Frame Kernel()=>preKernel??=pre!.Validate(binding);
    public void ConsiderCandidate(Vector3 point,Vector3 normal)
    {
        if(!CallbackReady())return;
        try
        {
            if(pre==null||!eligible.TryGetValue(pairObject,out bool angular)){CallbackFault(5);return;}
            if(!ContactValid(point,normal)){CallbackFault(2);return;}
            if(!angular||!AngularMotionFrame.MotionInBounds(pre.Motion)||!AngularMotionFrame.MotionInBounds(remaining)
                ||!binding.ContainsArm(pre.Com,point))return;
            var kernel=Kernel();var raw=kernel.Inspect(pre.Motion,point,normal);var shadow=kernel.Inspect(remaining,point,normal);
            if(!raw.Eligible||!shadow.Eligible)return;
            var result=kernel.Shadow(remaining,point,normal);
            // A candidate must be payable after f32 rounding BEFORE ranking.
            if(result.Branch!="shadow_applied")return;
            double score=Math.Min(raw.NormalEnergy,shadow.NormalEnergy);
            var contact=new Contact(point,normal);
            if(angularCandidate==null||score>angularCandidate.Score||
                (score==angularCandidate.Score&&Earlier(contact,angularCandidate.Contact)))
                angularCandidate=new(contact,score,result.Output);
        }
        catch(Exception){CallbackFault(4);}
    }
    public bool TryAdmit(uint objectId,Vector3 legacyPoint,Vector3 legacyNormal)
    {
        if(!CallbackReady())return false;
        try
        {
            if(!eligible.TryGetValue(objectId,out bool total))return false;
            if(!ContactValid(legacyPoint,legacyNormal)){CallbackFault(2);return false;}
            if(admitted.Contains(objectId))return true;
            if(decisions.TryGetValue(objectId,out bool old))return old;
            if(decisions.Count>=Limit){CallbackFault(3);return false;}
            if(pre==null||pairObject!=objectId){CallbackFault(5);return false;}
            decisions.Add(objectId,false);
            // Preserve candidate14's final f32 normal normalization and predicate.
            legacyNormal/=legacyNormal.Length();
            var legacy=new Contact(legacyPoint,legacyNormal);
            string mode;Contact chosen;AngularContactResponse.Motion output;Contact? retained=null;
            if(LinearEligible(pre.Motion.Linear,legacyNormal,total)&&LinearEligible(remaining.Linear,legacyNormal,total))
            {
                Kernel(); // Any published witness must pass its strict frame bounds.
                mode=total?"total_linear":"normal_linear";chosen=legacy;
                output=new(total?FractureResponse.ReduceTotal(remaining.Linear,mass):FractureResponse.Reduce(remaining.Linear,legacyNormal,mass),remaining.Angular);
            }
            else
            {
                if(!total||angularCandidate==null||!binding.ContainsArm(pre.Com,legacyPoint))return false;
                mode="angular_corner";chosen=angularCandidate.Contact;output=angularCandidate.Output;retained=legacy;
            }
            if(receipts.Count>=Limit){CallbackFault(3);return false;}
            if(!AngularMotionFrame.MotionInBounds(output)){CallbackFault(4);return false;}
            remaining=output;admitted.Add(objectId);decisions[objectId]=true;
            receipts.Add(new(objectId,step,receipts.Count+1,chosen.Point,chosen.Normal,pre.Motion.Linear,mode,
                output,default,retained,null));return true;
        }
        catch(Exception){CallbackFault(4);return false;}
    }
    bool LinearEligible(Vector3 v,Vector3 normal,bool total)
    {
        double speed2=(double)v.X*v.X+(double)v.Y*v.Y+(double)v.Z*v.Z;
        double closing=(double)v.X*normal.X+(double)v.Y*normal.Y+(double)v.Z*normal.Z;
        return double.IsFinite(speed2)&&speed2<=625&&closing>=.1&&(total?.5*mass*speed2:.5*mass*closing*closing)>=8000;
    }
    public AngularContactResponse.Motion CompleteSubstep(AngularMotionFrame post,Action<uint> removeBody)
    {
        Check();
        var pending=receipts.Where(r=>r.Substep==step).ToArray();
        if(pending.Length==0)return post.Motion;
        if(pre==null||witnesses.Count>=6||witnesses.Any(w=>w.Substep==step))throw new InvalidOperationException("angular witness order");
        Kernel();var kernel=post.Validate(binding);var motion=post.Motion;
        var completed=new List<Receipt>(pending.Length);
        // Validate/recompute the ENTIRE step before mutating/removing any body.
        foreach(var receipt in pending)
        {
            string? branch=null;
            if(receipt.Mode=="angular_corner")
            {
                if(!binding.ContainsArm(post.Com,receipt.Point))throw new InvalidDataException("angular POST arm outside bound");
                var result=kernel.Post(motion,receipt.Point,receipt.Normal);branch=result.Branch;
                if(branch is not("applied" or "noop_nonclosing" or "noop_quantized"))throw new InvalidOperationException("unsupported angular solver branch");
                motion=result.Output;
            }
            else motion=new(receipt.Mode=="total_linear"?FractureResponse.ReduceTotal(motion.Linear,mass):
                FractureResponse.Reduce(motion.Linear,receipt.Normal,mass),motion.Angular);
            if(!AngularMotionFrame.MotionInBounds(motion))throw new InvalidDataException("angular solver motion outside bound");
            completed.Add(receipt with{SolverAfter=motion,SolverBranch=branch});
        }
        foreach(var receipt in completed)receipts[receipt.Order-1]=receipt;
        witnesses.Add(new(step,pre,post));
        foreach(var receipt in completed)removeBody(receipt.ObjectId);
        return motion;
    }
    static bool Earlier(Contact a,Contact b)
    {
        for(int i=0;i<6;i++)
        {
            uint x=BitConverter.SingleToUInt32Bits(i<3?a.Point[i]:a.Normal[i-3]),y=BitConverter.SingleToUInt32Bits(i<3?b.Point[i]:b.Normal[i-3]);
            if(x!=y)return x<y;
        }
        return false;
    }
    static bool Bounded(Vector3 v,float maximum)=>float.IsFinite(v.X)&&float.IsFinite(v.Y)&&float.IsFinite(v.Z)
        &&MathF.Abs(v.X)<=maximum&&MathF.Abs(v.Y)<=maximum&&MathF.Abs(v.Z)<=maximum;
    static bool ContactValid(Vector3 point,Vector3 normal)=>Bounded(point,2000)&&Bounded(normal,2)
        &&normal.Length()>=.999f&&normal.Length()<=1.001f;
}
