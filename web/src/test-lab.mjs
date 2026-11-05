// TESTVEH-01 stand flag (owner 2026-11-05). WOT091_TEST_LAB unset or "0": the main
// catalogues; "1": the test_lab variant with the stand-only test vehicles
// (config/test_vehicles.json). The same flag drives tools/test_vehicles.py.
const value = globalThis.process?.env?.WOT091_TEST_LAB;
if (value !== undefined && value !== '0' && value !== '1') {
  throw new Error('WOT091_TEST_LAB must be 0 or 1');
}
export const TEST_LAB = value === '1';
// Research catalogue identity of each mode (tools/test_vehicles.py).
export const RESEARCH_CATALOG_SHA256 = TEST_LAB
  ? '646b61935ed5a5111296a26258663d1910a4a03152fa399ef28bce227cf12492'
  : '1f6b20d1ba564e00186fed77a3da74c3bd9b135f0db30ffdef740fd5888ced80';
