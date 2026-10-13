/** Original Barracks303 over the shared sparse roster and free50 policy. */
import { nativeDismissalCrewOverview, isNativeDismissalCrewOverview } from './p04j-crew.mjs';
import { DISMISSAL_CREW_POLICY_SHA256 } from './p04d-crew.mjs';

export const BARRACKS_CREW_POLICY_SHA256 = 'e9a12e9000cc255679d5dad6d744943f325ae1982c5a21060a5996f62c433fd7';
const POLICY = 'test_lab.ms1-is7-barracks-recruitment.v1';
const requireValue = (v, message) => { if (!v) throw new Error(message); };
const integer = (v, lo, hi) => Number.isSafeInteger(v) && v >= lo && v <= hi;

export function nativeBarracksCrewOverview(profile) {
  requireValue(profile?.profile_version === 12 && integer(profile.snapshot_revision, 12, 2147483647)
    && profile.crew_service?.schema === 'p04k-native-barracks-recruitment.v1'
    && profile.crew_service.policy_sha256 === BARRACKS_CREW_POLICY_SHA256, 'Barracks profile required');
  const previous = structuredClone(profile);
  previous.profile_version = 11;
  previous.crew_service.schema = 'p04j-native-crew-dismissal.v1';
  previous.crew_service.policy_sha256 = DISMISSAL_CREW_POLICY_SHA256;
  const value = nativeDismissalCrewOverview(previous);
  value.crewService.version = 7; value.crewService.policy = POLICY;
  return value;
}

export function isNativeBarracksCrewOverview(value, id) {
  if (value?.crewService?.version !== 7 || value.crewService.policy !== POLICY
    || !integer(value.snapshotRevision, 12, 2147483647)) return false;
  const previous = structuredClone(value);
  previous.crewService.version = 6; previous.crewService.policy = 'test_lab.ms1-is7-crew-dismissal.v1';
  return isNativeDismissalCrewOverview(previous, id);
}

export function validateBarracksRecruitmentResponse(value, request) {
  requireValue(['recruited', 'rejected'].includes(value.status), 'Barracks response status');
  if (value.status === 'rejected') {
    requireValue(value.tankman_inventory_id === 0 && value.tankman_descriptor_hex === '', 'Rejected barracks response allocated identity');
    return;
  }
  const id = value.tankman_inventory_id, hex = value.tankman_descriptor_hex;
  const [shop, type, role, cost] = request.layout;
  requireValue(integer(request.wire_revision, 1, 2147483646) && shop === 3 && cost === 0
    && ((type === 3329 && [1, 3].includes(role)) || (type === 7169 && [1, 3, 4, 5].includes(role)))
    && integer(id, 4, 16) && typeof hex === 'string' && /^[0-9a-f]{50}$/.test(hex), 'Barracks result selection/passport bounds');
  const descriptor = Buffer.from([8, type >> 8, role, 50, 0, 0, 0, id, 0, id, 0, id, 0, 64, 6, 0, 0, 0, 0, 66, 0, 0, 0, 0, 0]);
  requireValue(descriptor.toString('hex') === hex, 'Barracks result descriptor/request mismatch');
  function encodedInt(n) {
    if (n <= 255) return Buffer.from([75, n]);
    const out = Buffer.alloc(n <= 65535 ? 3 : 5); out[0] = n <= 65535 ? 77 : 74;
    if (n <= 65535) out.writeUInt16LE(n, 1); else out.writeInt32LE(n, 1);
    return out;
  }
  const raw = text => Buffer.from(text, 'latin1');
  const delta = Buffer.concat([raw('\x80\x02}(U\x07prevRev'), encodedInt(request.wire_revision),
    raw('U\x03rev'), encodedInt(request.wire_revision + 1),
    raw('U\x09inventory}(K\x08}(U\x09compDescr}(K'), Buffer.from([id]), raw('U\x19'), descriptor,
    raw('uU\x07vehicle}(K'), Buffer.from([id]), raw('J\xff\xff\xff\xffuuuU\x05stats}(U\x0cfreeTMenLeftK'),
    Buffer.from([16 - id]), raw('uu.')]);
  requireValue(delta.toString('hex') === value.update_hex, 'Barracks delta/ext/allocator mismatch');
}
