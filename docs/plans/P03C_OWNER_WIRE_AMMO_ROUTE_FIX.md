# P03C owner wire ammo route fix

## Goal

Close the gap found by the first owner manual test: the native map-drive
`READY_COMPOUND` path must append the already bounded MS-1 ammo candidate to
the binding body on the route that actually serves `drive_avatar`.

## Verified trigger

- The owner capture `owner-capture-060` contains one exact `READY_COMPOUND` at
  packet 74.
- The following server→client binding at packet 76 is 122 bytes.
- The decrypted capture has no `0x13 0x44` prefix and no exact candidate body.
- `receive_ready` dispatches map-drive sessions to `drive_avatar` while
  `self.drive.is_some()`; the later `queue_map_binding` branch is not reached
  for this live path.

## Scope

1. Append the existing typed `NativeAmmoUpdate` candidate to the binding body
   inside `drive_avatar` after all loadout/session validation and before the
   reliable enqueue.
2. Keep the existing 122-byte map-drive binding prefix unchanged.
3. Emit an explicit candidate diagnostic for this route with
   `native_receipt=NOT_RUN`.
4. Add a focused Rust test that exercises the real `drive_avatar` route and
   asserts a 133-byte body with the exact 11-byte candidate suffix.
5. Build and run the isolated gateway tests; do not launch the owner client in
   this phase.

## Acceptance

- Existing Rust tests remain green.
- The new focused test proves only server-side route bytes; native client HUD
  rendering remains unverified until the next owner test.
- Update STATUS and the P03 research record with the owner evidence and the
  new build receipt.

## Rollback

Revert the single `drive_avatar` route change and its focused test, then use
the previous build06 executable and owner evidence unchanged.
