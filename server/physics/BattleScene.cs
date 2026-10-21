using System.Globalization;
using System.Numerics;
using System.Text.Json;
using JoltPhysicsSharp;

namespace MapDrive;

// IPC7 deliberately has one world, one update per substep and one batch reply.
internal static class BattleScene
{
    sealed record TankContact(int A, int B, int Substep, Vector3 Point, Vector3 Normal, Vector3 Relative);
    // MAPS-02: first overlap of one hull with one falling atom sensor in a batch.
    sealed record ColumnContact(uint Object, int Slot, int Substep, Vector3 Point, Vector3 Normal, Vector3 Velocity);
    const int MaxColumnContactsPerActor = 16;
    public static int Run(string[] args)
    {
        if ((args.Length != 8 && args.Length != 10) || args[0] != "--battle-scene" || args[2] != "--scene-sha256" || args[4] != "--local-root" ||
            args[6] != "--generation" || (args.Length == 10 && args[8] != "--diagnostics") ||
            !uint.TryParse(args[7], NumberStyles.None, CultureInfo.InvariantCulture, out uint generation) || generation == 0)
            throw new InvalidDataException("expected pinned battle-scene/local-root/generation");
        string root = Path.GetFullPath(args[5]);
        var manifest = BattleSceneInput.Load(root, args[1], args[3]);
        using var input = Console.OpenStandardInput(); using var output = Console.OpenStandardOutput();
        using var bootstrap = CheckedInput.Json(BattleSceneInput.ReadLine(input) ?? throw new InvalidDataException("IPC7 missing bootstrap"));
        var scene = BattleSceneInput.Scene(bootstrap.RootElement, manifest, generation, 0, "restore_scene");
        if (!Foundation.Init(false)) throw new InvalidOperationException("Jolt initialization failed");
        try
        {
            using var diagnostics = args.Length == 10 ? new MixedContactDiagnostics(root, args[9]) : null;
            RunWorld(root, manifest, generation, scene, input, output, diagnostics);
        }
        finally { Foundation.Shutdown(); }
        return 0;
    }
    static void RunWorld(string root, BattleSceneInput.Manifest manifest, uint generation, CheckedInput.Scene scene, Stream input, Stream output,
        MixedContactDiagnostics? diagnostics)
    {
        using var pairs = new ObjectLayerPairFilterTable(2); pairs.EnableCollision(0, 1); pairs.EnableCollision(1, 1);
        using var broad = new BroadPhaseLayerInterfaceTable(2, 2); broad.MapObjectToBroadPhaseLayer(0, 0); broad.MapObjectToBroadPhaseLayer(1, 1);
        using var filter = new ObjectVsBroadPhaseLayerFilterTable(broad, 2, pairs, 2);
        using var jobs = new InlineJobSystem();
        using var world = new PhysicsSystem(new PhysicsSystemSettings
        {
            MaxBodies = Math.Max(32, (manifest.Catalog?.Entries.Length ?? 0) + (manifest.Catalog?.Columns.Length ?? 0) + manifest.Actors.Length + 8),
            MaxBodyPairs = 8192, MaxContactConstraints = 8192,
            ObjectLayerPairFilter = pairs, BroadPhaseLayerInterface = broad, ObjectVsBroadPhaseLayerFilter = filter
        });
        // Resolve dynamic hull pairs at the same four collision steps already
        // used by stock/extended profiles. Keep the single-body MS-1/IS-7
        // route at its accepted P05B step policy.
        int collisionSteps=manifest.Actors.Length > 1 || manifest.Actors.Any(a=>a.Kind is "t26" or "t34" or "t3485" or "wt-e100-128" or "fv215b-183")?TrackedBodySettings.StockCollisionSteps:1;
        var bodies = world.BodyInterface;
        var c = manifest.Actors[0].Config;
        using var terrain = CheckedInput.LoadMesh(root, c.GetProperty("terrain"), manifest.Map);
        var catalogShapes = new Dictionary<uint, MeshShape>();
        using var obstacles = manifest.Catalog == null ? CheckedInput.LoadMesh(root, c.GetProperty("obstacles"), manifest.Map) :
            CheckedInput.LoadCatalogMesh(root, c.GetProperty("obstacles"), manifest.Map, manifest.Catalog, out catalogShapes);
        var statics = new HashSet<BodyID>(); var catalogBodies = new Dictionary<uint, BodyID>();
        var catalogIds = new Dictionary<uint, uint>();
        var pending = new HashSet<uint>(); var claims = new Dictionary<uint, int>();
        var claimOrder = new List<(uint Object, int Slot, int Substep)>();
        var tanks = new List<BattleTank>(); var tankIds = new Dictionary<uint, BattleTank>();
        var tankContacts = new Dictionary<(int, int), TankContact>();
        var columnBodies = new Dictionary<uint, BodyID>(); var columnIds = new Dictionary<uint, uint>();
        var columnSeen = new HashSet<(int, uint)>(); var columnOrder = new List<ColumnContact>(); var columnPerActor = new Dictionary<int, int>();
        var diagnosticContacts = new Dictionary<(int, uint), object>();
        int diagnosticContactsOmitted = 0;
        using var prepass = manifest.Catalog == null ? null : new WholeObjectContactPrepass(world.Settings);
        int substep = 0, callbackCount = 0, callbackFault = 0; bool capture = false;
        long tick = 0, sequence = 0;
        BodyID AddStatic(Shape shape, Vector3 position)
        {
            using var creation = new BodyCreationSettings(shape, position, Quaternion.Identity, MotionType.Static, 0) { Friction = 1 };
            var body = bodies.CreateBody(creation); bodies.AddBody(body.ID, Activation.DontActivate); statics.Add(body.ID); return body.ID;
        }
        var terrainId = AddStatic(terrain, Vector3.Zero); var obstacleId = AddStatic(obstacles, Vector3.Zero);
        foreach (var entry in catalogShapes)
        {
            if (!scene.Ids.Contains(entry.Key))
            {
                var id = AddStatic(entry.Value, Vector3.Zero); catalogBodies.Add(entry.Key, id); catalogIds.Add(id.ID, entry.Key);
            }
            entry.Value.Dispose();
        }
        // Non-blocking falling atom triggers: static sensors never push a tank.
        // Committed fallen columns are absent, exactly like removed catalog bodies.
        foreach (var entry in manifest.Catalog?.Columns ?? [])
        {
            if (scene.Ids.Contains(entry.ObjectId)) continue;
            using var shape = CheckedInput.TriggerShape(manifest.Catalog!.Triggers!, entry);
            using var creation = new BodyCreationSettings(shape, Vector3.Zero, Quaternion.Identity, MotionType.Static, 0) { IsSensor = true };
            var body = bodies.CreateBody(creation); bodies.AddBody(body.ID, Activation.DontActivate); statics.Add(body.ID);
            columnBodies.Add(entry.ObjectId, body.ID); columnIds.Add(body.ID.ID, entry.ObjectId);
        }
        var bounds = c.GetProperty("bounds_xz");
        float minX = bounds[0].GetSingle(), minZ = bounds[1].GetSingle(), maxX = bounds[2].GetSingle(), maxZ = bounds[3].GetSingle();
        using var xWall = new BoxShape(new Vector3(.5f, 500, (maxZ - minZ) / 2 + 1));
        using var zWall = new BoxShape(new Vector3((maxX - minX) / 2 + 1, 500, .5f));
        AddStatic(xWall, new(minX - .5f, 0, (maxZ + minZ) / 2)); AddStatic(xWall, new(maxX + .5f, 0, (maxZ + minZ) / 2));
        AddStatic(zWall, new((maxX + minX) / 2, 0, minZ - .5f)); AddStatic(zWall, new((maxX + minX) / 2, 0, maxZ + .5f));
        void Contact(in Body body1, in Body body2, in ContactManifold m, ref ContactSettings settings)
        {
            if (!capture || callbackFault != 0) return;
            try
            {
                jobs.CheckThread();
                if (m.IsNull || m.PointCount == 0) return;
                if (++callbackCount > 24576) throw new InvalidOperationException("IPC7 contact callback bound");
                bool first = tankIds.TryGetValue(body1.ID.ID, out var a), second = tankIds.TryGetValue(body2.ID.ID, out var b);
                if (diagnostics != null && (first || second))
                {
                    // Private observation of the first actual manifold per
                    // actor/body pair in this batch, before fracture policy.
                    // Never changes a contact, body or the public IPC frame.
                    var actor = first ? a! : b!; var otherBody = first ? body2 : body1;
                    var key = (actor.Source.Slot, otherBody.ID.ID);
                    if (!diagnosticContacts.ContainsKey(key))
                    {
                        if (diagnosticContacts.Count == 64) diagnosticContactsOmitted++;
                        else
                        {
                            float depth = m.PenetrationDepth;
                            if (!float.IsFinite(depth)) throw new InvalidOperationException("nonfinite diagnostic manifold");
                            string otherKind = first && second ? "tank" : otherBody.ID == terrainId ? "terrain" :
                                otherBody.ID == obstacleId ? "static_obstacles" : catalogIds.ContainsKey(otherBody.ID.ID) ? "catalog_object" :
                                columnIds.ContainsKey(otherBody.ID.ID) ? "falling_atom_trigger" : "map_boundary";
                            diagnosticContacts.Add(key, new { slot = actor.Source.Slot, other_body_id = otherBody.ID.ID,
                                other_kind = otherKind, substep, penetration_depth_m = depth,
                                point = AngularMotionFrame.V(first ? m.GetWorldSpaceContactPointOn1(0) : m.GetWorldSpaceContactPointOn2(0)),
                                normal_actor_to_other = AngularMotionFrame.V(first ? m.WorldSpaceNormal : -m.WorldSpaceNormal) });
                        }
                    }
                }
                if (first && second)
                {
                    // Physical tank contact always remains solid; it never enters catalog energy policy.
                    bool ordered = a!.Source.Slot < b!.Source.Slot;
                    var lo = ordered ? a : b; var hi = ordered ? b : a;
                    var key = (lo.Source.Slot, hi.Source.Slot);
                    if (!tankContacts.ContainsKey(key)) tankContacts.Add(key, new(key.Item1, key.Item2, substep,
                        ordered ? m.GetWorldSpaceContactPointOn1(0) : m.GetWorldSpaceContactPointOn2(0),
                        ordered ? m.WorldSpaceNormal : -m.WorldSpaceNormal, lo.PreVelocity - hi.PreVelocity));
                    return;
                }
                if (first == second) return;
                var tank = first ? a! : b!; var other = first ? body2 : body1;
                if (columnIds.TryGetValue(other.ID.ID, out uint columnId))
                {
                    // Report only; the domain decides. Further overlaps beyond the
                    // per-actor bound remain sensor callbacks for a later batch.
                    settings.IsSensor = true;
                    int slot = tank.Source.Slot;
                    if (!columnSeen.Contains((slot, columnId)) && columnPerActor.GetValueOrDefault(slot) < MaxColumnContactsPerActor)
                    {
                        columnSeen.Add((slot, columnId)); columnPerActor[slot] = columnPerActor.GetValueOrDefault(slot) + 1;
                        columnOrder.Add(new(columnId, slot, substep, first ? m.GetWorldSpaceContactPointOn1(0) : m.GetWorldSpaceContactPointOn2(0),
                            Vector3.Normalize(first ? m.WorldSpaceNormal : -m.WorldSpaceNormal), tank.PreVelocity));
                    }
                    return;
                }
                if (tank.Fracture == null || !catalogIds.TryGetValue(other.ID.ID, out uint objectId)) return;
                if (claims.TryGetValue(objectId, out _)) { settings.IsSensor = true; return; }
                var point = first ? m.GetWorldSpaceContactPointOn1(0) : m.GetWorldSpaceContactPointOn2(0);
                var normal = first ? m.WorldSpaceNormal : -m.WorldSpaceNormal;
                tank.Fracture.CallbackThreadCheck(); tank.Fracture.Check();
                if (tank.Fracture.NeedsPrepass(objectId))
                {
                    tank.Fracture.BeginPair(objectId);
                    prepass!.Query(world, first ? body1 : body2, other, tank.PreVelocity, point, normal, tank.Fracture.ConsiderCandidate);
                    if (prepass.Fault) throw new InvalidOperationException("IPC7 contact prepass fault");
                    point = prepass.Point; normal = prepass.Normal;
                }
                if (tank.Fracture.TryAdmit(objectId, point, normal))
                {
                    // First qualifying actual callback owns the one debit and global removal.
                    claims.Add(objectId, tank.Source.Slot); claimOrder.Add((objectId, tank.Source.Slot, substep)); settings.IsSensor = true;
                }
            }
            catch { callbackFault = 1; } // Checked immediately after native update; no success frame follows.
        }
        world.OnContactAdded += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, m, ref s);
        world.OnContactPersisted += (PhysicsSystem _, in Body a, in Body b, in ContactManifold m, ref ContactSettings s) => Contact(a, b, m, ref s);
        void Advance(BattleSceneInput.Control[] controls, int count)
        {
            for (int i = 0; i < count; i++)
            {
                substep = i + 1;
                foreach (var tank in tanks) tank.BeforeStep(controls[tank.Source.Slot], substep, capture);
                var result = world.Update(1f / 60, collisionSteps, jobs); jobs.CheckThread();
                if (callbackFault != 0 || result != PhysicsUpdateError.None) throw new InvalidOperationException("IPC7 Jolt contact/update fault");
                var post = capture ? tanks.Select(t => AngularMotionFrame.Capture(t.Body, t.Source.Binding)).ToArray() : [];
                foreach (var tank in tanks)
                {
                    tank.Fracture?.Check();
                    if (capture && tank.Fracture != null)
                    {
                        var motion = tank.Fracture.CompleteSubstep(post[tank.Source.Slot], id =>
                        {
                            if (!claims.TryGetValue(id, out int owner) || owner != tank.Source.Slot || !pending.Add(id) || !catalogBodies.TryGetValue(id, out var body))
                                throw new InvalidOperationException("IPC7 global fracture claim mismatch");
                            bodies.RemoveBody(body);
                        });
                        bodies.SetLinearVelocity(tank.Body.ID, motion.Linear);
                        if (!AngularMotionFrame.SameBits(post[tank.Source.Slot].Motion.Angular, motion.Angular)) bodies.SetAngularVelocity(tank.Body.ID, motion.Angular);
                    }
                    bool hullContact = tankContacts.Values.Any(c => c.A == tank.Source.Slot || c.B == tank.Source.Slot);
                    tank.HoldForwardAgainstContact(hullContact, controls[tank.Source.Slot].Throttle);
                    tank.AfterStep();
                }
                tick++;
            }
        }
        void Write(string kind)
        {
            var v = AngularMotionFrame.V;
            var line = (manifest.Catalog?.Columns.Length ?? 0) > 0 ? JsonSerializer.SerializeToUtf8Bytes(new
            {
                version = 7, @event = kind, generation, manifest_sha256 = manifest.Hash, catalog_sha256 = manifest.Catalog!.Hash,
                seq = sequence, tick, settle_ticks = 180, map = manifest.Map, scene_version = scene.Version, scene_sha256 = scene.Hash,
                actors = tanks.Select(t => t.State()).ToArray(),
                tank_contacts = tankContacts.OrderBy(p => p.Key).Select(p => new { slot_a = p.Value.A, slot_b = p.Value.B, substep = p.Value.Substep,
                    point = v(p.Value.Point), normal = v(p.Value.Normal), relative_velocity = v(p.Value.Relative) }).ToArray(),
                fracture_claims = claimOrder.Select((p, i) => new { object_id = p.Object, slot = p.Slot, substep = p.Substep, order = i + 1 }).ToArray(),
                column_contacts = columnOrder.Select((p, i) => new { object_id = p.Object, slot = p.Slot, substep = p.Substep, order = i + 1,
                    point = v(p.Point), normal = v(p.Normal), velocity = v(p.Velocity) }).ToArray()
            }) : JsonSerializer.SerializeToUtf8Bytes(new
            {
                version = 7, @event = kind, generation, manifest_sha256 = manifest.Hash, catalog_sha256 = manifest.Catalog?.Hash ?? BattleSceneInput.EmptyCatalogHash,
                seq = sequence, tick, settle_ticks = 180, map = manifest.Map, scene_version = scene.Version, scene_sha256 = scene.Hash,
                actors = tanks.Select(t => t.State()).ToArray(),
                tank_contacts = tankContacts.OrderBy(p => p.Key).Select(p => new { slot_a = p.Value.A, slot_b = p.Value.B, substep = p.Value.Substep,
                    point = v(p.Value.Point), normal = v(p.Value.Normal), relative_velocity = v(p.Value.Relative) }).ToArray(),
                fracture_claims = claimOrder.Select((p, i) => new { object_id = p.Object, slot = p.Slot, substep = p.Substep, order = i + 1 }).ToArray()
            });
            if (line.Length > BattleSceneInput.MaxOutputBytes) throw new InvalidDataException("IPC7 output size bound");
            output.Write(line); output.WriteByte(10); output.Flush();
        }
        try
        {
            foreach (var actor in manifest.Actors) { var tank = new BattleTank(world, actor, manifest.Catalog); tanks.Add(tank); tankIds.Add(tank.Body.ID.ID, tank); }
            Advance(tanks.Select(_ => BattleSceneInput.Control.Stop).ToArray(), 180);
            foreach (var tank in tanks) tank.CheckSettled();
            diagnostics?.Write(0, tick, tanks.Select(t => t.Metrics(BattleSceneInput.Control.Stop)).ToArray(), [], 0);
            Write("ready");
            for (byte[]? raw; (raw = BattleSceneInput.ReadLine(input)) != null;)
            {
                using var document = CheckedInput.Json(raw); var request = document.RootElement;
                if (request.GetProperty("op").GetString() == "sync_removed")
                {
                    var next = BattleSceneInput.Scene(request, manifest, generation, sequence, "sync_removed");
                    if (scene.Ids.Any(id => !next.Ids.Contains(id)) || pending.Any(id => !next.Ids.Contains(id))) throw new InvalidDataException("IPC7 scene omits committed/prepared removal");
                    var delta = next.Ids.Where(id => !scene.Ids.Contains(id)).ToArray();
                    if (delta.Any(id => !catalogBodies.ContainsKey(id) && !columnBodies.ContainsKey(id))) throw new InvalidDataException("IPC7 unavailable catalog body");
                    foreach (uint id in delta)
                    {
                        if (columnBodies.Remove(id, out var sensor))
                        {
                            bodies.RemoveAndDestroyBody(sensor); statics.Remove(sensor); columnIds.Remove(sensor.ID); continue;
                        }
                        var body = catalogBodies[id];
                        if (pending.Remove(id)) bodies.DestroyBody(body); else bodies.RemoveAndDestroyBody(body);
                        statics.Remove(body); catalogIds.Remove(body.ID); catalogBodies.Remove(id);
                    }
                    scene = next;
                    var ack = JsonSerializer.SerializeToUtf8Bytes(new { version = 7, @event = "scene_synced", generation,
                        manifest_sha256 = manifest.Hash, catalog_sha256 = manifest.Catalog?.Hash ?? BattleSceneInput.EmptyCatalogHash,
                        advance_seq = sequence, tick, scene_version = scene.Version, removed_object_ids = scene.Ids, scene_sha256 = scene.Hash });
                    output.Write(ack); output.WriteByte(10); output.Flush(); continue;
                }
                var controls = BattleSceneInput.Advance(request, manifest, generation, sequence, scene);
                if (pending.Count > 0) throw new InvalidDataException("IPC7 prepared fracture requires scene commit");
                callbackCount = 0; callbackFault = 0; tankContacts.Clear(); claims.Clear(); claimOrder.Clear();
                columnSeen.Clear(); columnOrder.Clear(); columnPerActor.Clear();
                diagnosticContacts.Clear(); diagnosticContactsOmitted = 0;
                foreach (var tank in tanks) tank.BeginAdvance();
                capture = true; Advance(controls, 6); capture = false;
                foreach (var tank in tanks)
                    foreach (var receipt in (tank.Fracture?.Receipts ?? []).OrderBy(r => r.ObjectId))
                        tank.ObjectContacts.Add(new { object_id = receipt.ObjectId, kind = "hull", substep = receipt.Substep,
                            point = AngularMotionFrame.V(receipt.Point), normal = AngularMotionFrame.V(receipt.Normal), velocity = AngularMotionFrame.V(receipt.Velocity) });
                sequence++;
                diagnostics?.Write(sequence, tick, tanks.Select(t => t.Metrics(controls[t.Source.Slot])).ToArray(),
                    diagnosticContacts.Values.ToArray(), diagnosticContactsOmitted);
                Write(pending.Count == 0 ? "state" : "prepared");
            }
        }
        finally
        {
            capture = false;
            foreach (var tank in tanks.AsEnumerable().Reverse()) tank.Dispose();
            foreach (var id in statics)
                if (catalogIds.TryGetValue(id.ID, out uint objectId) && pending.Contains(objectId)) bodies.DestroyBody(id);
                else bodies.RemoveAndDestroyBody(id);
        }
    }
}
