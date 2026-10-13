using System.Numerics;

namespace MapDrive;

// Explicit approximate policy: reserve from pre-solver velocity, suppress only
// that pair, then dissipate from the actual post-solver velocity. Never refund
// velocity lost to terrain, a surviving wall, or another contact.
internal sealed class FractureResponse
{
    public const string Policy = "test_lab-fence-energy-v1";
    public const int EnergyJ = 8000, MaxFractures = 32;
    public sealed record Receipt(uint ObjectId, int Substep, int Order, Vector3 Point, Vector3 Normal,
        Vector3 Velocity, Vector3 BudgetBefore, Vector3 BudgetAfter, Vector3 SolverBefore, Vector3 SolverAfter, int EnergyJ);
    private readonly float mass;
    private readonly int ownerThread = Environment.CurrentManagedThreadId;
    private readonly HashSet<uint> eligible;
    private readonly Dictionary<uint, bool> decisions = new();
    private readonly HashSet<uint> admitted = new();
    private readonly List<Receipt> receipts = new();
    private int fault;
    private int substep;
    private Vector3 velocity, budget;
    public IReadOnlyList<Receipt> Receipts => receipts;

    public FractureResponse(float massKg, CheckedInput.CatalogSpec catalog)
    {
        if (!float.IsFinite(massKg) || massKg < 1000 || massKg > 100000 || !catalog.Fractures)
            throw new InvalidDataException("fracture profile/mass mismatch");
        mass = massKg;
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
        return double.IsFinite(speed2) && speed2 >= 1 && speed2 <= 625 && closing >= .1
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
