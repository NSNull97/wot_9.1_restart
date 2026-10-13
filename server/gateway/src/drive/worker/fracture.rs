//! Verified receipts for the explicitly approximate IPC5 contact policies. This
//! validates bounded server-worker output; it does not trust client impacts.
use super::*;

pub(super) const POLICY: &str = "test_lab-fence-energy-v1";
pub(super) const WHOLE_POLICY: &str = "test_lab-whole-object-energy-v1";
pub(super) const TOTAL_POLICY: &str = "test_lab-fence-total-energy-v1";
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
fn eligible(v: [f32; 3], n: [f32; 3], mass: f32, whole_response: bool) -> bool {
    let closing = dot(v,n);
    (if whole_response{0.}else{1.} ..=625.).contains(&dot(v,v)) && closing >= 0.1
        && 0.5*f64::from(mass)*closing*closing >= f64::from(ENERGY)
}
fn reduced(v: [f32; 3], n: [f32; 3], mass: f32) -> [f32; 3] {
    let closing = dot(v,n);
    if closing <= 0. { return v; }
    let after = (closing*closing - 2.*f64::from(ENERGY)/f64::from(mass)).max(0.).sqrt();
    std::array::from_fn(|i| (f64::from(v[i])-f64::from(n[i])*(closing-after)) as f32)
}
fn total_eligible(v: [f32; 3], n: [f32; 3], mass: f32) -> bool {
    let speed2=dot(v,v);
    (0. ..=625.).contains(&speed2) && dot(v,n)>=0.1
        && 0.5*f64::from(mass)*speed2>=f64::from(ENERGY)
}
fn total_reduced(v: [f32; 3], mass: f32) -> [f32; 3] {
    let energy=0.5*f64::from(mass)*dot(v,v);
    if energy<=f64::from(ENERGY){return [0.;3];}
    let factor=(1.-f64::from(ENERGY)/energy).sqrt();
    v.map(|component|(f64::from(component)*factor) as f32)
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
        let entry=spec.entries().iter().find(|entry|entry.object_id()==id).ok_or_else(bad)?;
        let total_response=spec.version()==7 && entry.ram_response()==Some("total_linear");
        let whole_response=matches!(spec.version(),6|7);
        if !ids.insert(id) || !(1..=6).contains(&substep) || order!=index as u64+1
            || uint(&row["energy_j"])?!=u64::from(ENERGY)
            || !(entry.kind()=="fragile" || whole_response && entry.kind()=="tree") || entry.ram_energy_j()!=ENERGY {
            return Err(bad());
        }
        let receipt = Receipt { object_id:id, substep, order:order as u8,
            point:vector(&row["point"],-2000.,2000.)?, normal:vector(&row["normal"],-1.,1.)?,
            velocity:vector(&row["velocity"],-25.,25.)?, budget_before:vector(&row["budget_before"],-25.,25.)?,
            budget_after:vector(&row["budget_after"],-25.,25.)?, solver_before:vector(&row["solver_before"],-25.,25.)?,
            solver_after:vector(&row["solver_after"],-25.,25.)?, energy_j:ENERGY };
        let admissible=|v|if total_response{total_eligible(v,receipt.normal,map.mass_kg)}
            else{eligible(v,receipt.normal,map.mass_kg,whole_response)};
        // The new double-to-f32 radial operation has identical specified
        // intermediates on the pinned platform. Do not apply the older,
        // deliberately wider Vector3/MathF tolerance to a total-energy debit.
        let debit_matches=|before,after|if total_response{after==total_reduced(before,map.mass_kg)}
            else{close(after,reduced(before,receipt.normal,map.mass_kg))};
        if (dot(receipt.normal,receipt.normal)-1.).abs()>0.0001
            || !contacts.iter().any(|contact|contact.object_id==id && contact.kind=="hull"
                && contact.substep==substep && contact.point==receipt.point && contact.normal==receipt.normal
                && contact.velocity==receipt.velocity)
            || !admissible(receipt.velocity) || !admissible(receipt.budget_before)
            || !debit_matches(receipt.budget_before,receipt.budget_after)
            || !debit_matches(receipt.solver_before,receipt.solver_after)
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
        assert!(eligible([0.,0.,4.],n,1000.,false));
        assert!(!eligible([0.,0.,f32::from_bits(4f32.to_bits()-1)],n,1000.,false));
        assert!(eligible([0.,0.,25.],n,1000.,false));
        assert!(!eligible([1.,0.,25.],n,1000.,false));
    }
    #[test]fn whole_response_uses_normal_energy_without_legacy_speed_floor_or_tangent_debit(){
        let n=[0.,0.,1.];
        assert!(eligible([0.,0.,0.8],n,68190.,true));
        assert!(!eligible([0.,0.,0.8],n,68190.,false));
        assert!(!eligible([0.,0.,0.8],n,4691.,true));
        for v in [[5.,0.,0.],[5.,0.,-2.],[5.,0.,0.1]] {assert!(!eligible(v,n,68190.,true));}
        let fast=[3.,0.,5.];
        let light=reduced(fast,n,4691.);let heavy=reduced(fast,n,68190.);
        assert_eq!(light[0],3.);assert_eq!(heavy[0],3.);assert_eq!(heavy[1],0.);
        assert!(heavy[2]>light[2]&&light[2]>0.&&heavy[2]<5.);
        for (mass,v) in [(4691.,light),(68190.,heavy)] {
            let dissipated=0.5*f64::from(mass)*(dot(fast,fast)-dot(v,v));
            assert!((dissipated-8000.).abs()<0.1);
        }
        // An admitted obstacle cannot refund an independent solid-wall stop.
        assert_eq!(reduced([3.,0.,0.],n,68190.),[3.,0.,0.]);
    }
    #[test]fn whole_tree_receipt_requires_matching_catalog_energy_and_exact_contact(){
        let spec=catalog::tests::whole_spec(1);let mut map=super::super::tests::map();map.mass_kg=68190.;
        let mut row=value(1);let velocity=[0.,0.,0.8];
        let after=reduced(velocity,[0.,0.,1.],map.mass_kg);
        for key in ["velocity","budget_before","solver_before"]{row[key]=serde_json::json!(velocity);}
        for key in ["budget_after","solver_after"]{row[key]=serde_json::json!(after);}
        let mut c=contact(1);c.velocity=velocity;
        assert_eq!(parse(&serde_json::json!([row.clone()]),&[c.clone()],&spec,&map,1).unwrap().len(),1);
        let old=catalog::tests::fracture_spec(1);
        assert!(parse(&serde_json::json!([row.clone()]),&[c.clone()],&old,&map,1).is_err());
        row["solver_after"]=serde_json::json!(velocity);
        assert!(parse(&serde_json::json!([row]),&[c],&spec,&map,1).is_err());
    }
    #[test]fn total_admission_has_exact_energy_incoming_and_speed_boundaries(){
        let x=[1.,0.,0.];let z=[0.,0.,1.];
        assert!(total_eligible([4.,0.,0.],x,1000.));
        assert!(!total_eligible([f32::from_bits(4f32.to_bits()-1),0.,0.],x,1000.));
        assert!(total_eligible([4.,0.,0.1],z,1000.));
        assert!(!total_eligible([4.,0.,f32::from_bits(0.1f32.to_bits()-1)],z,1000.));
        assert!(total_eligible([25.,0.,0.],x,1000.));
        for v in [[25.,0.,0.1],[4.,0.,0.],[4.,0.,-0.1],[0.;3],[f32::NAN,0.,1.],[f32::INFINITY,0.,1.]] {
            assert!(!total_eligible(v,z,1000.));
        }
        for mass in [4691.,68190.] {
            let grazing=[3.,0.,0.2];assert!(total_eligible(grazing,z,mass));
            assert!(!eligible(grazing,z,mass,true));
        }
    }
    #[test]fn total_debit_is_radial_finite_and_cannot_refund_a_solver_stop(){
        for mass in [1000.,4691.,68190.,100000.] {
            for v in [[3.,1.,5.],[-3.,-1.,5.],[0.,0.,0.1],[0.;3]] {
                let after=total_reduced(v,mass);let before_energy=0.5*f64::from(mass)*dot(v,v);
                let loss=before_energy-0.5*f64::from(mass)*dot(after,after);
                assert!((loss-before_energy.min(8000.)).abs()<0.5);
                assert!(after.iter().zip(v).all(|(a,b)|a.is_finite() && a.abs()<=b.abs() && *a*b>=0.));
                if before_energy<=8000. {assert_eq!(after,[0.;3]);}
                else {for i in 0..3 {assert!((f64::from(after[i])*f64::from(v[2])-f64::from(after[2])*f64::from(v[i])).abs()<0.00001);}}
            }
        }
        assert_eq!(total_reduced([0.;3],68190.),[0.;3]);
        assert_eq!(total_reduced([0.,0.,4.],1000.),[0.;3]);
    }
    fn mode_row(id:u32,order:u8,raw:[f32;3],budget:[f32;3],solver:[f32;3],mass:f32,total:bool)->Value {
        let n=[0.,0.,1.];let reduce=|v|if total{total_reduced(v,mass)}else{reduced(v,n,mass)};
        serde_json::json!({"object_id":id,"substep":1,"order":order,"point":[0.,0.,0.],"normal":n,
            "velocity":raw,"budget_before":budget,"budget_after":reduce(budget),
            "solver_before":solver,"solver_after":reduce(solver),"energy_j":8000})
    }
    #[test]fn total_receipt_requires_new_catalog_actual_hull_contact_and_exact_debit(){
        let spec=catalog::tests::response_spec(&[("fragile","total_linear")]);let map=super::super::tests::map();
        let raw=[3.,0.,0.2];let row=mode_row(1,1,raw,raw,[0.;3],map.mass_kg,true);
        let mut c=contact(1);c.velocity=raw;
        assert_eq!(parse(&serde_json::json!([row.clone()]),&[c.clone()],&spec,&map,1).unwrap().len(),1);
        for old in [catalog::tests::fracture_spec(1),catalog::tests::whole_spec(1),
            catalog::tests::response_spec(&[("fragile","normal_linear")])] {
            assert!(parse(&serde_json::json!([row.clone()]),&[c.clone()],&old,&map,1).is_err());
        }
        assert!(parse(&serde_json::json!([row.clone()]),&[],&spec,&map,1).is_err());
        let mut wheel=c.clone();wheel.kind="wheel".into();
        assert!(parse(&serde_json::json!([row.clone()]),&[wheel],&spec,&map,1).is_err());
        let mut changed=row.clone();let v=vector(&changed["budget_after"],-25.,25.).unwrap();
        changed["budget_after"][0]=serde_json::json!(f32::from_bits(v[0].to_bits()+1));
        assert!(parse(&serde_json::json!([changed]),&[c.clone()],&spec,&map,1).is_err());
        for key in ["budget_after","solver_after"] {
            let mut changed=row.clone();changed[key]=serde_json::json!(raw);
            assert!(parse(&serde_json::json!([changed]),&[c.clone()],&spec,&map,1).is_err());
        }
        let mut changed=row;changed["ram_response"]="normal_linear".into();
        assert!(parse(&serde_json::json!([changed]),&[c],&spec,&map,1).is_err());
    }
    #[test]fn total_and_normal_receipts_share_one_budget_in_both_orders(){
        let map=super::super::tests::map();let raw=[3.,0.,5.];let solver=[2.,0.,4.];
        for first_total in [false,true] {
            let modes=if first_total{[("fragile","total_linear"),("tree","normal_linear")]}
                else{[("tree","normal_linear"),("fragile","total_linear")]};
            let spec=catalog::tests::response_spec(&modes);
            let first=mode_row(1,1,raw,raw,solver,map.mass_kg,first_total);
            let second=mode_row(2,2,raw,vector(&first["budget_after"],-25.,25.).unwrap(),
                vector(&first["solver_after"],-25.,25.).unwrap(),map.mass_kg,!first_total);
            let mut c1=contact(1);c1.velocity=raw;let mut c2=c1.clone();c2.object_id=2;
            let contacts=[c1,c2];let rows=serde_json::json!([first,second]);
            assert_eq!(parse(&rows,&contacts,&spec,&map,1).unwrap().len(),2);
            let mut reset=rows.clone();reset[1]=mode_row(2,2,raw,raw,solver,map.mass_kg,!first_total);
            assert!(parse(&reset,&contacts,&spec,&map,1).is_err());
            for key in ["budget_before","solver_before"] {
                let mut changed=rows.clone();changed[1][key]=serde_json::json!(raw);
                assert!(parse(&changed,&contacts,&spec,&map,1).is_err());
            }
            let mut duplicate=rows;duplicate[1]["object_id"]=1.into();
            assert!(parse(&duplicate,&contacts,&spec,&map,1).is_err());
        }
    }
    #[test]fn total_receipts_cannot_spend_raw_energy_again_after_budget_exhaustion(){
        let spec=catalog::tests::response_spec(&[("fragile","total_linear");2]);let map=super::super::tests::map();
        let raw=[0.,0.,2.];let first=mode_row(1,1,raw,raw,raw,map.mass_kg,true);
        let remaining=vector(&first["budget_after"],-25.,25.).unwrap();
        assert!(total_eligible(raw,[0.,0.,1.],map.mass_kg));assert!(!total_eligible(remaining,[0.,0.,1.],map.mass_kg));
        let second=mode_row(2,2,raw,remaining,remaining,map.mass_kg,true);
        let mut c1=contact(1);c1.velocity=raw;let mut c2=c1.clone();c2.object_id=2;
        assert!(parse(&serde_json::json!([first,second]),&[c1,c2],&spec,&map,1).is_err());
    }
    #[test]fn total_double_arithmetic_matches_pinned_csharp_scalar_and_mixed_witnesses(){
        let path=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/evidence/20261013-p05b-tracked-handling-01/night-fence-components04/witnesses.json");
        let raw=std::fs::read(path).unwrap();
        assert_eq!(format!("{:x}",Sha256::digest(&raw)),"5d1dbd90c751c6fe6796db921780320f23b59af6e9b16715d417e752d21e706b");
        let data:Value=serde_json::from_slice(&raw).unwrap();assert_eq!(data["profile"],TOTAL_POLICY);
        let rows=data["witnesses"].as_array().unwrap();assert_eq!(rows.len(),95);let mut scalar=0;let mut mixed=0;
        for row in rows {
            let name=row["name"].as_str().unwrap();let mass=number(&row["mass"],1000.,100000.).unwrap();
            let v=vector(&row["input"],-30.,30.).unwrap();let n=vector(&row["normal"],-1.,1.).unwrap();
            if name=="mixed_True"||name=="mixed_False" {
                let first=vector(&row["first_after"],-25.,25.).unwrap();let second=vector(&row["second_after"],-25.,25.).unwrap();
                if name=="mixed_True"{assert_eq!(first,total_reduced(v,mass));assert!(close(second,reduced(first,n,mass)));}
                else{assert!(close(first,reduced(v,n,mass)));assert_eq!(second,total_reduced(first,mass));}
                mixed+=1;
            }else{
                let after=total_reduced(v,mass);let bits=row["after_bits"].as_array().unwrap();assert_eq!(bits.len(),3);
                assert_eq!(after,vector(&row["total_after"],-30.,30.).unwrap(),"{name}");
                for i in 0..3 {assert_eq!(u64::from(after[i].to_bits()),bits[i].as_u64().unwrap(),"{name} component {i}");}
                assert_eq!(total_eligible(v,n,mass),row["eligible"].as_bool().unwrap(),"{name}");scalar+=1;
            }
        }
        assert_eq!((scalar,mixed),(93,2));
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
