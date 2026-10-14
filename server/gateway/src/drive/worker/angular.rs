//! Closed IPC6 decoding. Float values become f32 before any physical arithmetic.
use super::*;
use crate::gateway091::shared::ram_proof::{self as proof, After, BodyBinding, FrameProof, FullMotion, Geometry, Mode, Profile, Receipt, SolverBranch, Witness};

fn array<const N:usize>(v:&Value,lo:f32,hi:f32)->io::Result<[f32;N]> {
    let a=v.as_array().filter(|a|a.len()==N).ok_or_else(bad)?;let mut out=[0.;N];
    for (slot,value) in out.iter_mut().zip(a){*slot=number(value,lo,hi)?;}Ok(out)
}
fn after(v:&Value)->io::Result<After>{fields(v,&["linear_velocity","angular_velocity"])?;
    Ok(After{v:array(&v["linear_velocity"],-25.,25.)?,w:array(&v["angular_velocity"],-20.,20.)?})}
fn full(v:&Value)->io::Result<FullMotion>{fields(v,&["com","rotation_xyzw","linear_velocity","angular_velocity","inverse_inertia_row_major"])?;
    Ok(FullMotion{com:array(&v["com"],-2000.,2000.)?,rotation:array(&v["rotation_xyzw"],-1.,1.)?,
        motion:After{v:array(&v["linear_velocity"],-25.,25.)?,w:array(&v["angular_velocity"],-20.,20.)?},
        inertia:array(&v["inverse_inertia_row_major"],-1.,1.)?})}
fn geometry(v:&Value)->io::Result<Geometry>{Ok(Geometry{point:array(&v["point"],-2000.,2000.)?,normal:array(&v["normal"],-1.,1.)?})}
pub(super) fn parse(state:&Value,contacts:&[ObjectContact],spec:&CatalogSpec,profile:Profile,seq:u32)->io::Result<Arc<FrameProof>> {
    fields(state,&["position","direction","speed","rspeed","contacts","linear_velocity","angular_velocity",
        "wheel_contact_masks","object_contacts","fractures","body_binding","motion_witnesses"])?;
    let b=&state["body_binding"];fields(b,&["inverse_mass","principal_inverse_diagonal","inertia_rotation_xyzw"])?;
    let binding=BodyBinding{inverse_mass:number(&b["inverse_mass"],0.,1.)?,principal:array(&b["principal_inverse_diagonal"],0.,1.)?,
        inertia_rotation:array(&b["inertia_rotation_xyzw"],-1.,1.)?};
    let rows=state["motion_witnesses"].as_array().filter(|a|a.len()<=6).ok_or_else(bad)?;
    let mut witnesses=Vec::with_capacity(rows.len());
    for row in rows {fields(row,&["substep","pre","post_solver"])?;
        witnesses.push(Witness{substep:u8::try_from(uint(&row["substep"])?).map_err(|_|bad())?,pre:full(&row["pre"])?,post:full(&row["post_solver"])?});}
    let rows=state["fractures"].as_array().filter(|a|a.len()<=32&&(seq!=0||a.is_empty())).ok_or_else(bad)?;
    let mut receipts=Vec::with_capacity(rows.len());
    for row in rows {
        let mode=match text(row,"mode")?{"normal_linear"=>Mode::Normal,"total_linear"=>Mode::Total,"angular_corner"=>Mode::Angular,_=>return Err(bad())};
        let mut keys=vec!["object_id","substep","order","point","normal","mode","budget_after","solver_after","energy_j"];
        if mode==Mode::Angular {keys.extend(["legacy_linear_candidate","solver_branch"]);}fields(row,&keys)?;
        let (legacy,solver_branch)=if mode==Mode::Angular {
            fields(&row["legacy_linear_candidate"],&["point","normal"])?;
            let branch=match text(row,"solver_branch")?{"applied"=>SolverBranch::Applied,"noop_nonclosing"=>SolverBranch::Nonclosing,"noop_quantized"=>SolverBranch::Quantized,_=>return Err(bad())};
            (Some(geometry(&row["legacy_linear_candidate"])?),Some(branch))
        }else{(None,None)};
        receipts.push(Receipt{object_id:u32::try_from(uint(&row["object_id"])?).map_err(|_|bad())?,
            substep:u8::try_from(uint(&row["substep"])?).map_err(|_|bad())?,order:u8::try_from(uint(&row["order"])?).map_err(|_|bad())?,
            geometry:geometry(row)?,mode,budget_after:after(&row["budget_after"])?,solver_after:after(&row["solver_after"])?,
            energy_j:u32::try_from(uint(&row["energy_j"])?).map_err(|_|bad())?,legacy,solver_branch});
    }
    let frame=FrameProof{profile,binding,witnesses,receipts};
    frame.validate(|id|spec.entries().iter().find(|e|e.object_id()==id).and_then(|e|match e.ram_response(){
        Some("normal_linear")=>Some(proof::Allowed::Normal),Some(proof::FALLBACK)=>Some(proof::Allowed::Fallback),_=>None}))?;
    for r in &frame.receipts {let pre=frame.witness(r.substep)?.pre;
        if !contacts.iter().any(|c|c.object_id==r.object_id&&c.kind=="hull"&&c.substep==r.substep
            &&proof::bits(c.point,r.geometry.point)&&proof::bits(c.normal,r.geometry.normal)&&proof::bits(c.velocity,pre.motion.v)){return Err(bad());}}
    Ok(Arc::new(frame))
}
/// Compatibility view for existing prepare/ACK bookkeeping and logs only.
/// Domain admission always retains and validates the complete typed proof.
pub(super) fn legacy_receipts(frame:&FrameProof)->io::Result<Vec<fracture::Receipt>> {
    frame.receipts.iter().enumerate().map(|(i,r)|{
        let w=frame.witness(r.substep)?;let previous=i.checked_sub(1).map(|j|&frame.receipts[j]).filter(|p|p.substep==r.substep);
        Ok(fracture::Receipt{object_id:r.object_id,substep:r.substep,order:r.order,point:r.geometry.point,normal:r.geometry.normal,
            velocity:w.pre.motion.v,budget_before:previous.map_or(w.pre.motion.v,|p|p.budget_after.v),budget_after:r.budget_after.v,
            solver_before:previous.map_or(w.post.motion.v,|p|p.solver_after.v),solver_after:r.solver_after.v,energy_j:r.energy_j})
    }).collect()
}

#[cfg(test)]
#[path="angular_tests.rs"]
pub(super) mod tests;
