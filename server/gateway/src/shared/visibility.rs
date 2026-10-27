//! Bounded server-only recipient interest policy, test_lab v1.
//!
//! This computes desired sets, not native enter/create/leave acknowledgement.
//! Inputs are authoritative world slots/poses and mounted profile ranges.
//! Sight points are supplied from server geometry. No native ID or packet state
//! enters this module. Camouflage, bushes, radio and retention are not modeled.
use std::io;

pub(crate) const MAX_ACTORS: usize = super::model::MAX_ACTORS;
/// Same finite coordinate ceiling as the existing terrain/obstacle query.
pub(crate) const MAX_COORDINATE: f32 = 10_000.;
/// Parser/domain safety bound, not a historical maximum effective view range.
pub(crate) const MAX_VIEW_RANGE: f32 = 1_000.;
pub(crate) const POLICY_REVISION: &str = "test_lab-interest-range-single-los-v1";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Allies {
    /// Explicit initial policy: own/allied tanks remain available to the client.
    Always,
    /// Useful stricter policy; own vehicle still remains available.
    RequireRangeAndLos,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct Actor {
    pub slot: usize,
    pub team: u8,
    pub position: [f32; 3],
    pub sight_point: [f32; 3],
    pub view_range: f32,
}

/// One read-only finite geometry query. `true` must mean unobstructed against
/// the current authoritative terrain AND applicable static obstacles.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct SightLine {
    pub recipient: usize,
    pub target: usize,
    pub start: [f32; 3],
    pub end: [f32; 3],
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct InterestSet(u32);
impl InterestSet {
    pub(crate) fn contains(self, slot: usize) -> bool {
        slot < MAX_ACTORS && self.0 & (1 << slot) != 0
    }
    pub(crate) fn slots(self) -> impl Iterator<Item = usize> {
        (0..MAX_ACTORS).filter(move |&slot| self.contains(slot))
    }
    fn insert(&mut self, slot: usize) { self.0 |= 1 << slot; }
}

/// No poses are retained or exposed in the result. Absent recipient slots do
/// not have a set. A complete matrix exists only after every query succeeds.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct InterestMatrix {
    recipients: InterestSet,
    desired: [InterestSet; MAX_ACTORS],
}
impl InterestMatrix {
    pub(crate) fn get(&self, recipient: usize) -> Option<InterestSet> {
        self.recipients.contains(recipient).then(|| self.desired[recipient])
    }
}

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

fn checked(actors: &[Actor]) -> io::Result<[Option<Actor>; MAX_ACTORS]> {
    if actors.is_empty() || actors.len() > MAX_ACTORS {
        return Err(invalid("visibility actor count outside 1..=6"));
    }
    let mut slots = [None; MAX_ACTORS];
    for &actor in actors {
        if actor.slot >= MAX_ACTORS || slots[actor.slot].is_some() {
            return Err(invalid("visibility duplicate/out-of-bounds domain slot"));
        }
        if !matches!(actor.team, 1 | 2) {
            return Err(invalid("visibility team outside 1..=2"));
        }
        if actor.position.into_iter().chain(actor.sight_point)
            .any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE) {
            return Err(invalid("visibility non-finite/out-of-bounds server point"));
        }
        if !actor.view_range.is_finite() || actor.view_range <= 0. || actor.view_range > MAX_VIEW_RANGE {
            return Err(invalid("visibility invalid mounted profile view range"));
        }
        slots[actor.slot] = Some(actor);
    }
    Ok(slots)
}

fn for_recipient<F>(recipient: Actor, slots: &[Option<Actor>; MAX_ACTORS], allies: Allies, los: &mut F)
    -> io::Result<InterestSet>
where F: FnMut(SightLine) -> io::Result<bool> {
    let mut desired = InterestSet::default();
    for &target in slots.iter().flatten() {
        if target.slot == recipient.slot || (target.team == recipient.team && allies == Allies::Always) {
            desired.insert(target.slot);
            continue;
        }
        // Explicit v1 policy: inclusive Euclidean 3-D centre distance. f64
        // avoids f32 overflow/rounding introduced by squaring bounded poses.
        let distance_squared = recipient.position.into_iter().zip(target.position)
            .map(|(a,b)| (f64::from(a)-f64::from(b)).powi(2)).sum::<f64>();
        if distance_squared > f64::from(recipient.view_range).powi(2) { continue; }
        let query = SightLine { recipient: recipient.slot, target: target.slot,
            start: recipient.sight_point, end: target.sight_point };
        let clear = los(query).map_err(|error| io::Error::new(error.kind(),
            format!("visibility LOS recipient_slot={} target_slot={}: {error}",recipient.slot,target.slot)))?;
        if clear { desired.insert(target.slot); }
    }
    Ok(desired)
}

/// Recompute at each publication from one coherent authoritative snapshot.
/// At most 6*5 LOS calls; no last-known permissive set or hysteresis survives.
/// Any invalid input or query error returns no matrix. The caller must suppress
/// publication on Err, rather than reuse a prior matrix with hidden enemies.
pub(crate) fn desired_sets<F>(actors: &[Actor], allies: Allies, mut los: F) -> io::Result<InterestMatrix>
where F: FnMut(SightLine) -> io::Result<bool> {
    let slots = checked(actors)?;
    let mut result = InterestMatrix { recipients: InterestSet::default(),
        desired: [InterestSet::default(); MAX_ACTORS] };
    for &actor in slots.iter().flatten() {
        result.desired[actor.slot] = for_recipient(actor,&slots,allies,&mut los)?;
        result.recipients.insert(actor.slot);
    }
    Ok(result)
}

/// Single-recipient variant with the same validation/closed-error semantics.
pub(crate) fn desired_set<F>(recipient: usize, actors: &[Actor], allies: Allies, mut los: F)
    -> io::Result<InterestSet>
where F: FnMut(SightLine) -> io::Result<bool> {
    let slots = checked(actors)?;
    let actor = slots.get(recipient).copied().flatten()
        .ok_or_else(|| invalid("visibility recipient absent from authoritative snapshot"))?;
    for_recipient(actor,&slots,allies,&mut los)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn actor(slot: usize, team: u8, x: f32, view_range: f32) -> Actor {
        Actor {slot,team,position:[x,0.,0.],sight_point:[x,2.,0.],view_range}
    }
    #[test] fn mixed_stock_ranges_are_asymmetric_inclusive_and_recomputed() {
        // Verified mounted T-18_Standart240 and IS-7 400, not a common radius.
        let mut actors = [actor(0,1,0.,240.),actor(1,2,300.,400.)];
        let matrix = desired_sets(&actors,Allies::Always,|_|Ok(true)).unwrap();
        assert_eq!(matrix.get(0).unwrap().slots().collect::<Vec<_>>(),vec![0]);
        assert_eq!(matrix.get(1).unwrap().slots().collect::<Vec<_>>(),vec![0,1]);
        actors[1].position[0]=240.;actors[1].sight_point[0]=240.;
        assert!(desired_set(0,&actors,Allies::Always,|_|Ok(true)).unwrap().contains(1));
        actors[1].position[0]=240.001;actors[1].sight_point[0]=240.001;
        assert!(!desired_set(0,&actors,Allies::Always,|_|Ok(true)).unwrap().contains(1));
        actors[1].position=[144.,192.,0.];actors[1].sight_point=[144.,194.,0.];
        assert!(desired_set(0,&actors,Allies::Always,|_|Ok(true)).unwrap().contains(1));
        actors[1].position[1]+=0.01;
        assert!(!desired_set(0,&actors,Allies::Always,|_|Ok(true)).unwrap().contains(1));
    }
    #[test] fn occlusion_and_server_sight_points_control_nearby_enemies_without_retention() {
        let actors = [actor(0,1,0.,240.),actor(1,2,100.,400.)];
        let mut wall = true;
        let mut query_count = 0;
        let mut query = |line:SightLine| {
            query_count+=1;assert_eq!(line.start,actors[line.recipient].sight_point);
            assert_eq!(line.end,actors[line.target].sight_point);Ok(!wall)
        };
        let hidden = desired_sets(&actors,Allies::Always,&mut query).unwrap();
        assert!(!hidden.get(0).unwrap().contains(1));assert!(!hidden.get(1).unwrap().contains(0));
        assert_eq!(query_count,2);wall=false;
        let visible = desired_sets(&actors,Allies::Always,|_|Ok(!wall)).unwrap();
        assert!(visible.get(0).unwrap().contains(1));
        wall=true;
        assert!(!desired_sets(&actors,Allies::Always,|_|Ok(!wall)).unwrap().get(0).unwrap().contains(1));
    }
    #[test] fn own_and_allied_policy_is_explicit_and_out_of_range_does_not_query_geometry() {
        let actors = [actor(0,1,0.,240.),actor(1,1,900.,240.),actor(2,2,901.,400.)];
        let matrix=desired_sets(&actors,Allies::Always,|line| {
            assert!(matches!((line.recipient,line.target),(1,2)|(2,1)));Ok(false)
        }).unwrap();
        assert_eq!(matrix.get(2).unwrap().slots().collect::<Vec<_>>(),vec![2]);
        let own=desired_set(0,&actors,Allies::Always,|_|panic!("no in-range enemy")).unwrap();
        assert_eq!(own.slots().collect::<Vec<_>>(),vec![0,1]);
        let strict=desired_set(0,&actors,Allies::RequireRangeAndLos,|_|panic!("all peers beyond range")).unwrap();
        assert_eq!(strict.slots().collect::<Vec<_>>(),vec![0]);assert!(!strict.contains(usize::MAX));
    }
    #[test] fn six_recipients_six_targets_are_bounded_and_order_independent() {
        let actors=std::array::from_fn::<_,6,_>(|slot|actor(slot,if slot%2==0{1}else{2},slot as f32*5.,400.));
        let mut queries=Vec::new();
        let matrix=desired_sets(&actors,Allies::Always,|line|{queries.push((line.recipient,line.target));Ok(true)}).unwrap();
        assert_eq!(queries.len(),18);assert!(queries.iter().all(|(a,b)|a!=b && a%2!=b%2));
        for slot in 0..6 {assert_eq!(matrix.get(slot).unwrap().slots().collect::<Vec<_>>(),(0..6).collect::<Vec<_>>());}
        assert!(matrix.get(6).is_none());assert!(matrix.get(usize::MAX).is_none());
        let mut reverse=actors;reverse.reverse();let mut reversed_queries=Vec::new();
        let reversed=desired_sets(&reverse,Allies::Always,|line|{reversed_queries.push((line.recipient,line.target));Ok(true)}).unwrap();
        assert_eq!(matrix,reversed);assert_eq!(queries,reversed_queries);
    }
    #[test] fn invalid_snapshot_is_rejected_before_any_geometry_query() {
        let good=[actor(0,1,0.,240.),actor(1,2,10.,400.)];
        for mutation in 0..10 {
            let mut actors=good;
            match mutation {
                0=>actors[1].slot=0,1=>actors[1].slot=MAX_ACTORS,2=>actors[1].team=0,3=>actors[1].team=3,
                4=>actors[1].sight_point[1]=f32::NAN,5=>actors[1].position[0]=f32::INFINITY,
                6=>actors[1].sight_point[0]=MAX_COORDINATE+1.,7=>actors[1].view_range=0.,
                8=>actors[1].view_range=f32::NAN,9=>actors[1].view_range=MAX_VIEW_RANGE+1.,_=>unreachable!(),
            }
            assert!(desired_sets(&actors,Allies::Always,|_|panic!("validation must precede LOS")).is_err(),"mutation{mutation}");
        }
        assert!(desired_sets(&[],Allies::Always,|_|panic!()).is_err());
        let too_many=vec![good[0];MAX_ACTORS+1];assert!(desired_sets(&too_many,Allies::Always,|_|panic!()).is_err());
        assert!(desired_set(5,&good,Allies::Always,|_|panic!()).is_err());
    }
    #[test] fn a_late_los_error_returns_no_partial_matrix_and_never_mutates_the_snapshot() {
        let actors=[actor(0,1,0.,240.),actor(1,2,10.,400.),actor(2,2,20.,400.)];let original=actors;
        let mut calls=0;
        let result=desired_sets(&actors,Allies::Always,|_| {
            calls+=1;if calls==2 {Err(io::Error::new(io::ErrorKind::TimedOut,"authored LOS failure"))} else {Ok(true)}
        });
        let error=result.unwrap_err();assert_eq!(error.kind(),io::ErrorKind::TimedOut);
        assert!(error.to_string().contains("recipient_slot=0 target_slot=2"));assert_eq!(calls,2);assert_eq!(actors,original);
        assert!(desired_set(0,&actors,Allies::Always,|_|Err(io::Error::other("no LOS provider"))).is_err());
    }
}
