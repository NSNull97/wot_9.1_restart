using System.Runtime.InteropServices;
using JoltPhysicsSharp;

namespace MapDrive;

// Pinned Native1.1.0 exports this callback job system. ThreadPool numThreads=0
// means auto, and numThreads=1 still runs jobs on the caller and a worker.
// Dispatch the native job function immediately; never block inside a callback.
internal sealed unsafe class InlineJobSystem : JobSystem
{
    [StructLayout(LayoutKind.Sequential)]
    private struct Config
    {
        public nint Context;
        public delegate* unmanaged<nint, delegate* unmanaged<nint, void>, nint, void> QueueJob;
        public delegate* unmanaged<nint, delegate* unmanaged<nint, void>, nint*, uint, void> QueueJobs;
        public uint MaxConcurrency;
        public uint MaxBarriers;
    }
    private sealed class Dispatch
    {
        public readonly int OwnerThread = Environment.CurrentManagedThreadId;
        public int WrongThread;
        public GCHandle Root;
    }
    private readonly Dispatch dispatch;
    [DllImport("joltc", CallingConvention = CallingConvention.Cdecl)]
    private static extern nint JPH_JobSystemCallback_Create(Config* config);

    public InlineJobSystem() : this(new Dispatch()) { }
    private InlineJobSystem(Dispatch state) : base(Create(state)) { dispatch = state; }
    private static nint Create(Dispatch state)
    {
        state.Root = GCHandle.Alloc(state);
        try
        {
            var config = new Config { Context = GCHandle.ToIntPtr(state.Root), QueueJob = &One,
                QueueJobs = &Many, MaxConcurrency = 1, MaxBarriers = 8 };
            nint handle = JPH_JobSystemCallback_Create(&config);
            if (handle == 0) throw new InvalidOperationException("inline job system creation failed");
            return handle;
        }
        catch { state.Root.Free(); throw; }
    }
    public void CheckThread()
    {
        if (Environment.CurrentManagedThreadId != dispatch.OwnerThread || Volatile.Read(ref dispatch.WrongThread) != 0)
            throw new InvalidOperationException("inline job callback left its owner thread");
    }
    private static void Execute(nint context, delegate* unmanaged<nint, void> callback, nint argument)
    {
        var state = (Dispatch)GCHandle.FromIntPtr(context).Target!;
        if (Environment.CurrentManagedThreadId != state.OwnerThread) Interlocked.Exchange(ref state.WrongThread, 1);
        // Still drain the job if the invariant breaks: dropping it could strand
        // a native barrier. The managed owner fails immediately after Update.
        callback(argument);
    }
    [UnmanagedCallersOnly]
    private static void One(nint context, delegate* unmanaged<nint, void> callback, nint argument)
        => Execute(context, callback, argument);
    [UnmanagedCallersOnly]
    private static void Many(nint context, delegate* unmanaged<nint, void> callback, nint* arguments, uint count)
    {
        for (uint i = 0; i < count; i++) Execute(context, callback, arguments[i]);
    }
    protected override void DisposeNative()
    {
        base.DisposeNative();
        if (dispatch.Root.IsAllocated) dispatch.Root.Free();
    }
}
