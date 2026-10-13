using System.Numerics;
using System.Collections;
using JoltPhysicsSharp;

namespace MapDrive;

// Explicit approximate policy: reserve from pre-solver velocity, suppress only
// that pair, then dissipate from the actual post-solver velocity. Never refund
// velocity lost to terrain, a surviving wall, or another contact.
internal sealed class FractureResponse
{
    public const string Policy = "test_lab-fence-energy-v1";
    public const string WholeObjectPolicy = "test_lab-whole-object-energy-v1";
    public const int EnergyJ = 8000, MaxFractures = 32;
    public sealed record Receipt(uint ObjectId, int Substep, int Order, Vector3 Point, Vector3 Normal,
        Vector3 Velocity, Vector3 BudgetBefore, Vector3 BudgetAfter, Vector3 SolverBefore, Vector3 SolverAfter, int EnergyJ);
    private readonly float mass;
    private readonly bool wholeObjectEnergy;
    private readonly int ownerThread = Environment.CurrentManagedThreadId;
    private readonly HashSet<uint> eligible;
    private readonly Dictionary<uint, bool> decisions = new();
    private readonly HashSet<uint> admitted = new();
    private readonly List<Receipt> receipts = new();
    private int fault;
    private int substep;
    private Vector3 velocity, budget;
    public IReadOnlyList<Receipt> Receipts => receipts;
    public bool NeedsWholeObjectPrepass(uint objectId) => wholeObjectEnergy && Environment.CurrentManagedThreadId == ownerThread
        && Volatile.Read(ref fault) == 0 && decisions.Count < MaxFractures && eligible.Contains(objectId)
        && !admitted.Contains(objectId) && !decisions.ContainsKey(objectId);
    public void CallbackValueFault() => Interlocked.Exchange(ref fault, 1);

    public FractureResponse(float massKg, CheckedInput.CatalogSpec catalog)
    {
        if (!float.IsFinite(massKg) || massKg < 1000 || massKg > 100000 || !catalog.Fractures)
            throw new InvalidDataException("fracture profile/mass mismatch");
        mass = massKg;
        wholeObjectEnergy = catalog.Version == 6;
        eligible = catalog.Entries.Where(e => e.RamEnergyJ == EnergyJ).Select(e => e.ObjectId).ToHashSet();
    }
    public void BeginAdvance()
    {
        Check(); decisions.Clear(); admitted.Clear(); receipts.Clear();
    }
    public void BeginSubstep(int step, Vector3 actualVelocity)
    {
        Check();
        if (step < 1 || step > 6 || !Bounded(actualVelocity, 256)) throw new InvalidDataException("fracture substep velocity invalid");
        substep = step; velocity = actualVelocity; budget = actualVelocity; decisions.Clear();
    }
    public void Check()
    {
        if (Environment.CurrentManagedThreadId != ownerThread || Volatile.Read(ref fault) != 0)
            throw new InvalidOperationException("fracture callback thread/value/count invariant failed");
    }
    public void CallbackThreadCheck()
    {
        if (Environment.CurrentManagedThreadId != ownerThread) Interlocked.Exchange(ref fault, 1);
    }
    // No exception crosses an unmanaged callback. Invalid data makes the owner
    // fail after Update; it never produces a prepared response.
    public bool TryAdmit(uint objectId, Vector3 point, Vector3 normal)
    {
        CallbackThreadCheck();
        if (Volatile.Read(ref fault) != 0 || !eligible.Contains(objectId)) return false;
        float length = normal.Length();
        if (!Bounded(point, 2000) || !Bounded(normal, 2) || length < .999f || length > 1.001f)
        { Interlocked.Exchange(ref fault, 1); return false; }
        if (admitted.Contains(objectId)) return true;
        if (decisions.TryGetValue(objectId, out bool old)) return old;
        if (decisions.Count >= MaxFractures) { Interlocked.Exchange(ref fault, 1); return false; }
        decisions.Add(objectId, false);
        normal /= length;
        if (!Eligible(velocity, normal) || !Eligible(budget, normal)) return false;
        if (receipts.Count >= MaxFractures) { Interlocked.Exchange(ref fault, 1); return false; }
        Vector3 before = budget; budget = Reduce(budget, normal, mass);
        admitted.Add(objectId); decisions[objectId] = true;
        receipts.Add(new Receipt(objectId, substep, receipts.Count + 1, point, normal, velocity,
            before, budget, Vector3.Zero, Vector3.Zero, EnergyJ));
        return true;
    }
    private bool Eligible(Vector3 v, Vector3 normal)
    {
        // Admission is recomputed by the gateway from these exact f32 values.
        // Use double products in both implementations at the hard threshold.
        double speed2 = (double)v.X * v.X + (double)v.Y * v.Y + (double)v.Z * v.Z;
        double closing = (double)v.X * normal.X + (double)v.Y * normal.Y + (double)v.Z * normal.Z;
        // The whole-object policy uses normal kinetic energy for the lower
        // bound. An independent 1m/s floor incorrectly rejects heavy tanks
        // whose slower closing motion already supplies the required energy.
        // Keep that historical project floor for catalog5 rollback/replay.
        return double.IsFinite(speed2) && (wholeObjectEnergy || speed2 >= 1) && speed2 <= 625 && closing >= .1
            && .5 * mass * closing * closing >= EnergyJ;
    }
    public Vector3 CompleteSubstep(Vector3 actualSolverVelocity, Action<uint> removeBody)
    {
        Check();
        if (!Bounded(actualSolverVelocity, 256)) throw new InvalidDataException("fracture solver velocity invalid");
        Vector3 result = actualSolverVelocity;
        for (int i = 0; i < receipts.Count; i++)
        {
            var receipt = receipts[i]; if (receipt.Substep != substep) continue;
            Vector3 before = result; result = Reduce(result, receipt.Normal, mass);
            receipts[i] = receipt with { SolverBefore = before, SolverAfter = result };
            removeBody(receipt.ObjectId);
        }
        return result;
    }
    public static Vector3 Reduce(Vector3 v, Vector3 normal, float massKg)
    {
        float closing = Vector3.Dot(v, normal);
        if (closing <= 0) return v;
        float remaining = MathF.Sqrt(MathF.Max(0, closing * closing - 2 * EnergyJ / massKg));
        return v - normal * (closing - remaining);
    }
    private static bool Bounded(Vector3 v, float maximum) => float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z)
        && MathF.Abs(v.X) <= maximum && MathF.Abs(v.Y) <= maximum && MathF.Abs(v.Z) <= maximum;
}

// Catalog6 only: decide from the whole real body pair before the first contact
// callback returns any constraint settings. Looking at a later manifold would
// be too late to undo an earlier solid constraint. This query never initiates
// destruction by itself: Program invokes it only after an actual hull callback.
internal sealed class WholeObjectContactPrepass : ICollection<CollideShapeResult>, IDisposable
{
    // Each catalog body has <=4096 source triangles; the query is a convex box
    // against this one mesh, not the complete map. Retain one copied candidate,
    // no native face spans. Any unexpected result/count fails outside callback.
    public const int MaxHits = 4096;
    private sealed class PairFilter : BodyFilter
    {
        public BodyID Target;
        protected override bool ShouldCollide(BodyID id) => id == Target;
        protected override bool ShouldCollideLocked(Body body) => body.ID == Target;
    }
    private readonly PairFilter filter = new();
    private CollideShapeSettings settings;
    private Vector3 velocity;
    public Vector3 Point { get; private set; }
    public Vector3 Normal { get; private set; }
    public bool SelectedQueryContact { get; private set; }
    public bool Fault { get; private set; }
    public int Count { get; private set; }
    public bool IsReadOnly => false;

    public WholeObjectContactPrepass(PhysicsSettings physics)
    {
        if (!float.IsFinite(physics.SpeculativeContactDistance) || physics.SpeculativeContactDistance < 0
            || physics.SpeculativeContactDistance > 1) throw new InvalidDataException("pair query separation bound");
        settings = new CollideShapeSettings { MaxSeparationDistance = physics.SpeculativeContactDistance,
            ActiveEdgeMode = physics.CheckActiveEdges ? ActiveEdgeMode.CollideOnlyWithActive : ActiveEdgeMode.CollideWithAll };
    }
    public void Query(PhysicsSystem world, Body tank, Body target, Vector3 incoming, Vector3 callbackPoint, Vector3 callbackNormal)
    {
        Reset(target.ID, incoming, callbackPoint, callbackNormal);
        settings.ActiveEdgeMovementDirection = incoming;
        // Contact callbacks hold the bodies locked. Calling a locking query or
        // BodyInterface here can deadlock; body access and NoLock are read-only.
        world.NarrowPhaseQueryNoLock.CollideShape(tank.Shape, Vector3.One, tank.GetCenterOfMassTransform(),
            settings, Vector3.Zero, CollisionCollectorType.AllHit, this, bodyFilter: filter);
    }
    internal void Reset(BodyID target, Vector3 incoming, Vector3 point, Vector3 normal)
    {
        filter.Target = target; velocity = incoming; Point = point; Normal = normal;
        Count = 0; Fault = false; SelectedQueryContact = false;
        if (!Bounded(incoming, 256) || !Bounded(point, 2000) || !Bounded(normal, 2)
            || normal.Length() < .999f || normal.Length() > 1.001f) Fault = true;
        else Normal = Vector3.Normalize(normal);
    }
    public void Add(CollideShapeResult hit)
    {
        if (Fault) return;
        if (++Count > MaxHits || hit.BodyID2 != filter.Target || !float.IsFinite(hit.PenetrationDepth)
            || hit.PenetrationDepth < -settings.MaxSeparationDistance - .001f)
        { Fault = true; return; }
        Consider(hit.ContactPointOn1, hit.PenetrationAxis);
    }
    internal void Consider(Vector3 point, Vector3 axis)
    {
        float length = axis.Length();
        if (!Bounded(point, 2000) || !Bounded(axis, 256) || !float.IsFinite(length) || length < 1e-6f)
        { Fault = true; return; }
        Vector3 normal = axis / length;
        double closing(Vector3 n) => (double)velocity.X * n.X + (double)velocity.Y * n.Y + (double)velocity.Z * n.Z;
        double candidate = closing(normal), current = closing(Normal);
        bool better = candidate > current;
        if (candidate == current)
        {
            // Stable exact tie break, independent of the query's hit ordering.
            for (int i = 0; i < 6; i++)
            {
                float a = i < 3 ? point[i] : normal[i - 3], b = i < 3 ? Point[i] : Normal[i - 3];
                int order = BitConverter.SingleToUInt32Bits(a).CompareTo(BitConverter.SingleToUInt32Bits(b));
                if (order != 0) { better = order < 0; break; }
            }
        }
        if (better) { Point = point; Normal = normal; SelectedQueryContact = true; }
    }
    private static bool Bounded(Vector3 v, float maximum) => float.IsFinite(v.X) && float.IsFinite(v.Y) && float.IsFinite(v.Z)
        && MathF.Abs(v.X) <= maximum && MathF.Abs(v.Y) <= maximum && MathF.Abs(v.Z) <= maximum;
    public void Dispose() => filter.Dispose();
    public void Clear() => throw new NotSupportedException();
    public bool Contains(CollideShapeResult item) => throw new NotSupportedException();
    public void CopyTo(CollideShapeResult[] array, int index) => throw new NotSupportedException();
    public bool Remove(CollideShapeResult item) => throw new NotSupportedException();
    public IEnumerator<CollideShapeResult> GetEnumerator() => throw new NotSupportedException();
    IEnumerator IEnumerable.GetEnumerator() => GetEnumerator();
}
