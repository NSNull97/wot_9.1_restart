//! Verified receipts for the explicitly approximate IPC5 fence policy. This
//! validates bounded server-worker output; it does not trust client impacts.
use super::*;

pub(super) const POLICY: &str = "test_lab-fence-energy-v1";
const ENERGY: u32 = 8_000;

#[derive(Clone, Debug, PartialEq)]
pub struct Receipt {
    pub object_id: u32,
    pub substep: u8,
    pub order: u8,
    pub point: [f32; 3],
    pub normal: [f32; 3],
    pub velocity: [f32; 3],
    pub budget_before: [f32; 3],
    pub budget_after: [f32; 3],
    pub solver_before: [f32; 3],
    pub solver_after: [f32; 3],
    pub energy_j: u32,
}

fn dot(a: [f32; 3], b: [f32; 3]) -> f64 {
    a.iter().zip(b).map(|(a,b)| f64::from(*a)*f64::from(b)).sum()
}
fn close(a: [f32; 3], b: [f32; 3]) -> bool {
    // C# Vector3/MathF and Rust validation may round f32 intermediate values
    // differently. Tolerance is for arithmetic only, not receipt identities.
    a.iter().zip(b).all(|(a,b)| (*a-b).abs() <= 0.0001*(1.+a.abs().max(b.abs())))
}
fn eligible(v: [f32; 3], n: [f32; 3], mass: f32) -> bool {
    let closing = dot(v,n);
    (1. ..=625.).contains(&dot(v,v)) && closing >= 0.1
        && 0.5*f64::from(mass)*closing*closing >= f64::from(ENERGY)
}
fn reduced(v: [f32; 3], n: [f32; 3], mass: f32) -> [f32; 3] {
    let closing = dot(v,n);
    if closing <= 0. { return v; }
    let after = (closing*closing - 2.*f64::from(ENERGY)/f64::from(mass)).max(0.).sqrt();
    std::array::from_fn(|i| (f64::from(v[i])-f64::from(n[i])*(closing-after)) as f32)
}
pub(super) fn parse(value: &Value, contacts: &[ObjectContact], spec: &CatalogSpec,
    map: &MapSpec, seq: u32) -> io::Result<Vec<Receipt>> {
    let rows = value.as_array().ok_or_else(bad)?;
    if rows.len()>32 || (seq==0 && !rows.is_empty()) || !map.mass_kg.is_finite()
        || !(1000. ..=100000.).contains(&map.mass_kg) { return Err(bad()); }
    let mut receipts: Vec<Receipt> = Vec::with_capacity(rows.len());
    let mut ids = BTreeSet::new();
    for (index,row) in rows.iter().enumerate() {
        fields(row,&["object_id","substep","order","point","normal","velocity","budget_before",
            "budget_after","solver_before","solver_after","energy_j"])?;
        let id = u32::try_from(uint(&row["object_id"])?).map_err(|_|bad())?;
        let substep = u8::try_from(uint(&row["substep"])?).map_err(|_|bad())?;
        let order = uint(&row["order"])?;
        if !ids.insert(id) || !(1..=6).contains(&substep) || order!=index as u64+1
            || uint(&row["energy_j"])?!=u64::from(ENERGY)
            || !spec.entries().iter().any(|entry|entry.object_id()==id && entry.kind()=="fragile" && entry.ram_energy_j()==ENERGY) {
            return Err(bad());
        }
        let receipt = Receipt { object_id:id, substep, order:order as u8,
            point:vector(&row["point"],-2000.,2000.)?, normal:vector(&row["normal"],-1.,1.)?,
            velocity:vector(&row["velocity"],-25.,25.)?, budget_before:vector(&row["budget_before"],-25.,25.)?,
            budget_after:vector(&row["budget_after"],-25.,25.)?, solver_before:vector(&row["solver_before"],-25.,25.)?,
            solver_after:vector(&row["solver_after"],-25.,25.)?, energy_j:ENERGY };
        if (dot(receipt.normal,receipt.normal)-1.).abs()>0.0001
            || !contacts.iter().any(|contact|contact.object_id==id && contact.kind=="hull"
                && contact.substep==substep && contact.point==receipt.point && contact.normal==receipt.normal
                && contact.velocity==receipt.velocity)
            || !eligible(receipt.velocity,receipt.normal,map.mass_kg)
            || !eligible(receipt.budget_before,receipt.normal,map.mass_kg)
            || !close(receipt.budget_after,reduced(receipt.budget_before,receipt.normal,map.mass_kg))
            || !close(receipt.solver_after,reduced(receipt.solver_before,receipt.normal,map.mass_kg))
            || dot(receipt.budget_after,receipt.budget_after)>dot(receipt.budget_before,receipt.budget_before)+0.001
            || dot(receipt.solver_after,receipt.solver_after)>dot(receipt.solver_before,receipt.solver_before)+0.001 {
            return Err(bad());
        }
        if let Some(previous)=receipts.last() {
            if substep<previous.substep { return Err(bad()); }
            if substep==previous.substep {
                if receipt.velocity!=previous.velocity || receipt.budget_before!=previous.budget_after
                    || receipt.solver_before!=previous.solver_after { return Err(bad()); }
            } else if receipt.budget_before!=receipt.velocity { return Err(bad()); }
        } else if receipt.budget_before!=receipt.velocity { return Err(bad()); }
        receipts.push(receipt);
    }
    Ok(receipts)
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    #[test]fn fracture_eligibility_uses_exact_double_boundary_and_total_speed_bound(){
        let n=[0.,0.,1.];
        assert!(eligible([0.,0.,4.],n,1000.));
        assert!(!eligible([0.,0.,f32::from_bits(4f32.to_bits()-1)],n,1000.));
        assert!(eligible([0.,0.,25.],n,1000.));
        assert!(!eligible([1.,0.,25.],n,1000.));
    }
    pub(in super::super) fn contact(id:u32)->ObjectContact {
        ObjectContact{object_id:id,kind:"hull".into(),substep:1,point:[0.;3],normal:[0.,0.,1.],velocity:[0.,0.,4.]}
    }
    pub(in super::super) fn value(id:u32)->Value {
        let before=[0.,0.,4.];
        serde_json::json!({"object_id":id,"order":1,"substep":1,"point":[0.,0.,0.],"normal":[0.,0.,1.],
            "velocity":before,"budget_before":before,"budget_after":reduced(before,[0.,0.,1.],4691.),
            "solver_before":[0.,0.,0.5],"solver_after":[0.,0.,0.],"energy_j":8000})
    }
    #[test]fn fracture_receipt_requires_exact_identity_energy_and_nonincreasing_solver(){
        let spec=catalog::tests::fracture_spec(2);let map=super::super::tests::map();let good=value(1);
        let check=|v:Value|parse(&serde_json::json!([v]),&[contact(1)],&spec,&map,1);
        assert_eq!(check(good.clone()).unwrap().len(),1);
        for (key,bad_value) in [
            ("object_id",serde_json::json!(2)),("substep",serde_json::json!(2)),("order",serde_json::json!(2)),
            ("point",serde_json::json!([1.,0.,0.])),("normal",serde_json::json!([0.,0.,0.9])),
            ("velocity",serde_json::json!([0.,0.,5.])),("budget_before",serde_json::json!([0.,0.,5.])),
            ("budget_after",serde_json::json!([0.,0.,4.])),("solver_after",serde_json::json!([0.,0.,1.])),
            ("energy_j",serde_json::json!(0)),("energy_j",serde_json::json!(8000.0))] {
            let mut changed=good.clone();changed[key]=bad_value;assert!(check(changed).is_err(),"{key}");
        }
        assert!(parse(&serde_json::json!([good.clone()]),&[contact(1)],&spec,&map,0).is_err());
        let mut repeated=good.clone();repeated["order"]=2.into();
        assert!(parse(&serde_json::json!([good,repeated]),&[contact(1)],&spec,&map,1).is_err());
    }
    #[test]fn fracture_receipts_chain_budget_and_solver_in_recorded_order(){
        let spec=catalog::tests::fracture_spec(2);let map=super::super::tests::map();let first=value(1);
        let mut second=value(2);second["order"]=2.into();second["budget_before"]=first["budget_after"].clone();
        let before=vector(&second["budget_before"],-25.,25.).unwrap();
        second["budget_after"]=serde_json::json!(reduced(before,[0.,0.,1.],map.mass_kg));
        second["solver_before"]=first["solver_after"].clone();second["solver_after"]=first["solver_after"].clone();
        let contacts=[contact(1),contact(2)];let rows=serde_json::json!([first,second]);
        assert_eq!(parse(&rows,&contacts,&spec,&map,1).unwrap().len(),2);
        for key in ["budget_before","solver_before"]{
            let mut changed=rows.clone();changed[1][key]=serde_json::json!([0.,0.,4.]);
            assert!(parse(&changed,&contacts,&spec,&map,1).is_err());
        }
        let mut changed=rows;changed[1]["order"]=1.into();assert!(parse(&changed,&contacts,&spec,&map,1).is_err());
    }
}
