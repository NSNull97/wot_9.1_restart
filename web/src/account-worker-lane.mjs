// One account's bridge workers run strictly in turn: a second caller waits for
// the running worker instead of starting beside it, a bounded number may wait
// and any further caller is refused. Each account service owns its own lane,
// so different accounts still run concurrently.
export function createAccountLane(maxPending, busyMessage) {
  if (!Number.isInteger(maxPending) || maxPending < 1) throw new Error('Account lane bound required');
  let tail = Promise.resolve(), pending = 0;
  const lane = async task => {
    if (pending >= maxPending) throw new Error(busyMessage);
    pending++;
    const previous = tail; let release;
    tail = new Promise(done => { release = done; });
    try { await previous; return await task(); }
    finally { pending--; release(); }
  };
  lane.pending = () => pending;
  return lane;
}
