//! IPC6 physical proof. No transport IDs enter the scalar kernel or FrameProof.
//! The separate context carries authority across the domain and replay boundary.
use std::{collections::BTreeSet, io, sync::Arc};
use super::ram_response::{self as scalar, Branch, Contact, Motion};

pub const POLICY: &str = "test_lab-fence-linear-angular-energy-v1";
pub const FALLBACK: &str = "total_linear_angular_fallback";
fn bad() -> io::Error { io::Error::new(io::ErrorKind::InvalidData,"angular frame proof") }
pub fn bits<const N:usize>(a:[f32;N],b:[f32;N])->bool { a.map(f32::to_bits)==b.map(f32::to_bits) }
fn dot(a:[f32;3],b:[f32;3])->f64 { let a=a.map(f64::from);let b=b.map(f64::from);(a[0]*b[0]+a[1]*b[1])+a[2]*b[2] }

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Profile { Ms1, Is7, T26, T34, T3485, WtE100128, Fv215b183,
    /// BATTLE-ANY: qualified generated profile (SHA, mass, box, getter bits from the registry).
    Generated(super::generated_vehicles::GeneratedId) }
// BW-01 wire codec (tools/bw01_wire_gen.py): Profile
impl crate::bw_wire::Wire for Profile {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;match self {Self::Ms1=>bw_o.tag(0),Self::Is7=>bw_o.tag(1),Self::T26=>bw_o.tag(2),Self::T34=>bw_o.tag(3),Self::T3485=>bw_o.tag(4),Self::WtE100128=>bw_o.tag(5),Self::Fv215b183=>bw_o.tag(6),Self::Generated(f0)=>{bw_o.tag(7);W::put(f0,bw_o);}}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;match bw_i.tag()? {0=>Ok(Self::Ms1),1=>Ok(Self::Is7),2=>Ok(Self::T26),3=>Ok(Self::T34),4=>Ok(Self::T3485),5=>Ok(Self::WtE100128),6=>Ok(Self::Fv215b183),7=>Ok(Self::Generated(W::get(bw_i)?)),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
impl Profile {
    pub fn for_vehicle(kind:super::vehicle_profile::VehicleKind)->Self {
        use super::vehicle_profile::VehicleKind;match kind {
            VehicleKind::Ms1=>Self::Ms1,
            VehicleKind::Is7=>Self::Is7,
            VehicleKind::T26=>Self::T26,
            VehicleKind::T34=>Self::T34,
            VehicleKind::T3485=>Self::T3485,
            VehicleKind::Wt128=>Self::WtE100128,
            VehicleKind::Fv183=>Self::Fv215b183,
            VehicleKind::Generated(id)=>Self::Generated(id),
        }
    }
    pub fn sha(self)->&'static str {match self {
        Self::Ms1=>"48f8ac675afafbe8605bd97bd92dc2c37f26673b65a548d4f0402b815f7ee9a1",
        Self::Is7=>"2b72923c904678b5471ca4c8e01125f787d0baeb8cf2153c322a126fa1b6cfd7",
        Self::T26=>"9674a5e9ef24b9f1c857845bd6021aeb302333ed2c3d52e92f07eb0bb85c7217",
        Self::T34=>"1ac77973e1ca2b18449102b814c23c9208e9b91f61d9f16afeb73a58f9d0583e",
        Self::T3485=>"ebe62bae0281f775b45f269a37919e86fbc99789eac789fc9368c42210880a0a",
        Self::Fv215b183=>"0e9eb47ba39b53592e1f7de6a302521ea8252bdb616df0d8f5dc10d2ab28b516",
        Self::WtE100128=>"85c810a944828d23d42ea8691142d16dc1cfb1c73156a6c7b7f11723d4dfd777",
        Self::Generated(id)=>&super::generated_vehicles::entry(id).qualified_sha256,
    }}
    pub fn mass(self)->f32 {match self {
        Self::Ms1=>4691.0,
        Self::Is7=>68190.0,
        Self::T26=>9302.0,
        Self::T34=>27940.0,
        Self::T3485=>32370.0,
        Self::Fv215b183=>60000.0,
        Self::WtE100128=>100000.0,
        Self::Generated(id)=>super::generated_vehicles::entry(id).mass_kg as f32,
    }}
    pub fn half(self)->[f32;3] {if let Self::Generated(id)=self{
        let h=&super::generated_vehicles::entry(id).physics["body_half_extents"];
        return std::array::from_fn(|i|h[i].as_f64().unwrap_or(f64::NAN) as f32);}
        match self {
        Self::Ms1=>[1062334726, 1058324871, 1073766889],
        Self::Is7=>[1070765540, 1057701716, 1080490562],
        Self::T26=>[1063348639, 1057918816, 1074313859],
        Self::T34=>[1067860166, 1060034181, 1077318550],
        Self::T3485=>[1067741503, 1060176048, 1077678709],
        Self::Fv215b183=>[1071931720, 1059939242, 1080605838],
        Self::WtE100128=>[1070290874, 1060339020, 1082354210],
        Self::Generated(_)=>unreachable!("returned above"),
    }.map(f32::from_bits)}
    pub fn binding(self)->BodyBinding {
        let (u,p,q)=match self {
            Self::Generated(id)=>{let e=super::generated_vehicles::entry(id);(e.inverse_mass_bits,e.principal_inverse_bits,e.inertia_rotation_bits)},
            Self::Ms1=>(962561921,[957270281, 957988763, 975566011],[1060439283, 1060439283, 0, 0]),
            Self::Is7=>(930482508,[909880447, 912106386, 930468834],[1060439283, 1060439283, 0, 0]),
            Self::T26=>(954299301,[947738559, 948617937, 966510618],[1060439283, 1060439283, 0, 0]),
            Self::T34=>(940973638,[926374033, 928078481, 944841139],[1060439283, 1060439283, 0, 0]),
            Self::T3485=>(939627237,[924265041, 925539494, 943103976],[1060439283, 1060439283, 0, 0]),
            Self::Fv215b183=>(931909477,[910983497, 913652340, 929452436],[1060439283, 1060439283, 0, 0]),
            Self::WtE100128=>(925353388,[902802560, 904396031, 925297667],[1060439283, 1060439283, 0, 0]),
        };
        BodyBinding{inverse_mass:f32::from_bits(u),principal:p.map(f32::from_bits),inertia_rotation:q.map(f32::from_bits)}
    }
    fn lever(self,p:[f32;3],com:[f32;3])->bool {
        let h=self.half().map(f64::from);let r=std::array::from_fn::<_,3,_>(|i|f64::from(p[i])-f64::from(com[i]));
        (r[0]*r[0]+r[1]*r[1])+r[2]*r[2] <= 4.*((h[0]*h[0]+h[1]*h[1])+h[2]*h[2])
    }
}
#[derive(Clone,Copy,Debug)]
pub struct BodyBinding {pub inverse_mass:f32,pub principal:[f32;3],pub inertia_rotation:[f32;4]}
// BW-01 wire codec (tools/bw01_wire_gen.py): BodyBinding
impl crate::bw_wire::Wire for BodyBinding {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{inverse_mass,principal,inertia_rotation}=self;W::put(inverse_mass,bw_o);W::put(principal,bw_o);W::put(inertia_rotation,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{inverse_mass:W::get(bw_i)?,principal:W::get(bw_i)?,inertia_rotation:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl PartialEq for BodyBinding {fn eq(&self,b:&Self)->bool {self.inverse_mass.to_bits()==b.inverse_mass.to_bits()
    &&bits(self.principal,b.principal)&&bits(self.inertia_rotation,b.inertia_rotation)}}
#[derive(Clone,Copy,Debug)]
pub struct After {pub v:[f32;3],pub w:[f32;3]}
// BW-01 wire codec (tools/bw01_wire_gen.py): After
impl crate::bw_wire::Wire for After {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{v,w}=self;W::put(v,bw_o);W::put(w,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{v:W::get(bw_i)?,w:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl PartialEq for After {fn eq(&self,b:&Self)->bool{bits(self.v,b.v)&&bits(self.w,b.w)}}
impl After {fn valid(self)->bool {self.v.iter().chain(&self.w).all(|v|v.is_finite())
    &&dot(self.v,self.v)<=625.&&self.w.iter().all(|v|v.abs()<=20.)}}
#[derive(Clone,Copy,Debug)]
pub struct FullMotion {pub com:[f32;3],pub rotation:[f32;4],pub motion:After,pub inertia:[f32;9]}
// BW-01 wire codec (tools/bw01_wire_gen.py): FullMotion
impl crate::bw_wire::Wire for FullMotion {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{com,rotation,motion,inertia}=self;W::put(com,bw_o);W::put(rotation,bw_o);W::put(motion,bw_o);W::put(inertia,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{com:W::get(bw_i)?,rotation:W::get(bw_i)?,motion:W::get(bw_i)?,inertia:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl PartialEq for FullMotion {fn eq(&self,b:&Self)->bool{bits(self.com,b.com)&&bits(self.rotation,b.rotation)
    &&self.motion==b.motion&&bits(self.inertia,b.inertia)}}
impl FullMotion {
    pub fn scalar(self,b:BodyBinding,a:After)->Motion {Motion{com:self.com,velocity:a.v,omega:a.w,inverse_mass:b.inverse_mass,
        inverse_inertia:std::array::from_fn(|i|std::array::from_fn(|j|self.inertia[i*3+j]))}}
    fn validate(self,b:BodyBinding)->io::Result<()> {
        scalar::verify_basis(self.scalar(b,self.motion),self.rotation,b.principal,b.inertia_rotation).map_err(|_|bad())?;
        // Inspect also enforces finite/SPD/motion bounds on frames with no angular receipt.
        scalar::inspect(self.scalar(b,self.motion),Contact{point:self.com,normal:[1.,0.,0.]}).map_err(|_|bad())?;Ok(())
    }
}
#[derive(Clone,Debug,PartialEq)]
pub struct Witness {pub substep:u8,pub pre:FullMotion,pub post:FullMotion}
// BW-01 wire codec (tools/bw01_wire_gen.py): Witness
impl crate::bw_wire::Wire for Witness {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{substep,pre,post}=self;W::put(substep,bw_o);W::put(pre,bw_o);W::put(post,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{substep:W::get(bw_i)?,pre:W::get(bw_i)?,post:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Mode {Normal,Total,Angular}
// BW-01 wire codec (tools/bw01_wire_gen.py): Mode
impl crate::bw_wire::Wire for Mode {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Normal=>bw_o.tag(0),Self::Total=>bw_o.tag(1),Self::Angular=>bw_o.tag(2),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Normal),1=>Ok(Self::Total),2=>Ok(Self::Angular),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum SolverBranch {Applied,Nonclosing,Quantized}
// BW-01 wire codec (tools/bw01_wire_gen.py): SolverBranch
impl crate::bw_wire::Wire for SolverBranch {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Applied=>bw_o.tag(0),Self::Nonclosing=>bw_o.tag(1),Self::Quantized=>bw_o.tag(2),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Applied),1=>Ok(Self::Nonclosing),2=>Ok(Self::Quantized),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug)]
pub struct Geometry {pub point:[f32;3],pub normal:[f32;3]}
// BW-01 wire codec (tools/bw01_wire_gen.py): Geometry
impl crate::bw_wire::Wire for Geometry {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{point,normal}=self;W::put(point,bw_o);W::put(normal,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{point:W::get(bw_i)?,normal:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl PartialEq for Geometry {fn eq(&self,b:&Self)->bool{bits(self.point,b.point)&&bits(self.normal,b.normal)}}
impl Geometry {pub fn scalar(self)->Contact{Contact{point:self.point,normal:self.normal}}
    fn valid(self)->bool {self.point.iter().chain(&self.normal).all(|v|v.is_finite())
        &&self.point.iter().all(|v|v.abs()<=2000.)&&self.normal.iter().all(|v|v.abs()<=1.)
        &&(dot(self.normal,self.normal)-1.).abs()<=0.0001}}
#[derive(Clone,Debug,PartialEq)]
pub struct Receipt {pub object_id:u32,pub substep:u8,pub order:u8,pub geometry:Geometry,pub mode:Mode,
    pub budget_after:After,pub solver_after:After,pub energy_j:u32,
    pub legacy:Option<Geometry>,pub solver_branch:Option<SolverBranch>}
// BW-01 wire codec (tools/bw01_wire_gen.py): Receipt
impl crate::bw_wire::Wire for Receipt {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{object_id,substep,order,geometry,mode,budget_after,solver_after,energy_j,legacy,solver_branch}=self;W::put(object_id,bw_o);W::put(substep,bw_o);W::put(order,bw_o);W::put(geometry,bw_o);W::put(mode,bw_o);W::put(budget_after,bw_o);W::put(solver_after,bw_o);W::put(energy_j,bw_o);W::put(legacy,bw_o);W::put(solver_branch,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{object_id:W::get(bw_i)?,substep:W::get(bw_i)?,order:W::get(bw_i)?,geometry:W::get(bw_i)?,mode:W::get(bw_i)?,budget_after:W::get(bw_i)?,solver_after:W::get(bw_i)?,energy_j:W::get(bw_i)?,legacy:W::get(bw_i)?,solver_branch:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Debug,PartialEq)]
pub struct FrameProof {pub profile:Profile,pub binding:BodyBinding,pub witnesses:Vec<Witness>,pub receipts:Vec<Receipt>}
// BW-01 wire codec (tools/bw01_wire_gen.py): FrameProof
impl crate::bw_wire::Wire for FrameProof {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{profile,binding,witnesses,receipts}=self;W::put(profile,bw_o);W::put(binding,bw_o);W::put(witnesses,bw_o);W::put(receipts,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{profile:W::get(bw_i)?,binding:W::get(bw_i)?,witnesses:W::get(bw_i)?,receipts:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Allowed {Normal,Fallback}

fn eligible(v:[f32;3],n:[f32;3],mass:f32,total:bool)->bool {let c=dot(v,n);let v2=dot(v,v);
    (0. ..=625.).contains(&v2)&&c>=0.1&&0.5*f64::from(mass)*(if total{v2}else{c*c})>=8000.}
fn reduce(v:[f32;3],n:[f32;3],mass:f32,total:bool)->[f32;3] {
    if total {let e=0.5*f64::from(mass)*dot(v,v);if e<=8000.{return [0.;3];}
        let factor=(1.-8000./e).sqrt();return v.map(|v|(f64::from(v)*factor)as f32);}
    let c=dot(v,n);if c<=0.{return v;}let after=(c*c-16000./f64::from(mass)).max(0.).sqrt();
    std::array::from_fn(|i|(f64::from(v[i])-f64::from(n[i])*(c-after))as f32)
}
fn debit(before:After,after:After,n:[f32;3],mass:f32,total:bool)->bool {
    let expected=reduce(before.v,n,mass,total);
    bits(before.w,after.w) && if total {bits(expected,after.v)} else {
        // Legacy arithmetic tolerance ONLY. All identities and the next chain seed remain exact bits.
        expected.iter().zip(after.v).all(|(a,b)|(*a-b).abs()<=0.0001*(1.+a.abs().max(b.abs())))
        &&dot(after.v,after.v)<=dot(before.v,before.v)+0.001 }
}
impl FrameProof {
    pub fn witness(&self,step:u8)->io::Result<&Witness>{self.witnesses.iter().find(|w|w.substep==step).ok_or_else(bad)}
    pub fn validate(&self,allowed:impl Fn(u32)->Option<Allowed>)->io::Result<()> {
        if self.binding!=self.profile.binding()||self.witnesses.len()>6||self.receipts.len()>32 {return Err(bad());}
        let steps=self.receipts.iter().map(|r|r.substep).collect::<BTreeSet<_>>();
        if self.witnesses.iter().map(|w|w.substep).collect::<Vec<_>>()!=steps.into_iter().collect::<Vec<_>>() {return Err(bad());}
        for w in &self.witnesses {if !(1..=6).contains(&w.substep){return Err(bad());}w.pre.validate(self.binding)?;w.post.validate(self.binding)?;}
        let mut ids=BTreeSet::new();let mut previous:Option<&Receipt>=None;
        for (i,r) in self.receipts.iter().enumerate() {
            if r.object_id==0||!ids.insert(r.object_id)||r.order as usize!=i+1||r.energy_j!=8000
                ||!r.geometry.valid()||!r.budget_after.valid()||!r.solver_after.valid()
                ||previous.is_some_and(|p|p.substep>r.substep) {return Err(bad());}
            let w=self.witness(r.substep)?;let same=previous.filter(|p|p.substep==r.substep);
            let budget=same.map_or(w.pre.motion,|p|p.budget_after);let solver=same.map_or(w.post.motion,|p|p.solver_after);
            let authority=allowed(r.object_id).ok_or_else(bad)?;
            match r.mode {
                Mode::Normal|Mode::Total=>{
                    let total=r.mode==Mode::Total;
                    if (total&&authority!=Allowed::Fallback)||(!total&&authority!=Allowed::Normal)
                        ||r.legacy.is_some()||r.solver_branch.is_some()
                        ||!eligible(w.pre.motion.v,r.geometry.normal,self.profile.mass(),total)
                        ||!eligible(budget.v,r.geometry.normal,self.profile.mass(),total)
                        ||!debit(budget,r.budget_after,r.geometry.normal,self.profile.mass(),total)
                        ||!debit(solver,r.solver_after,r.geometry.normal,self.profile.mass(),total){return Err(bad());}
                }
                Mode::Angular=>{
                    let legacy=r.legacy.ok_or_else(bad)?;
                    if authority!=Allowed::Fallback||!legacy.valid()
                        ||!self.profile.lever(legacy.point,w.pre.com)||!self.profile.lever(r.geometry.point,w.pre.com)
                        ||!self.profile.lever(r.geometry.point,w.post.com)
                        ||(eligible(w.pre.motion.v,legacy.normal,self.profile.mass(),true)
                            &&eligible(budget.v,legacy.normal,self.profile.mass(),true)){return Err(bad());}
                    let c=r.geometry.scalar();let raw=w.pre.scalar(self.binding,w.pre.motion);let remaining=w.pre.scalar(self.binding,budget);
                    if !scalar::inspect(raw,c).map_err(|_|bad())?.eligible() {return Err(bad());}
                    let shadow=scalar::shadow(remaining,c).map_err(|_|bad())?;
                    if shadow.branch!=Branch::ShadowApplied||r.budget_after!= (After{v:shadow.velocity,w:shadow.omega}) {return Err(bad());}
                    let post=scalar::post_solver(w.post.scalar(self.binding,solver),c).map_err(|_|bad())?;
                    let branch=match post.branch{Branch::Applied=>SolverBranch::Applied,Branch::NoopNonclosing=>SolverBranch::Nonclosing,
                        Branch::NoopQuantized=>SolverBranch::Quantized,_=>return Err(bad())};
                    if r.solver_branch!=Some(branch)||r.solver_after!=(After{v:post.velocity,w:post.omega}) {return Err(bad());}
                }
            }
            previous=Some(r);
        }Ok(())
    }
    pub fn final_motion(&self,v:[f32;3],w:[f32;3],rspeed:f32)->io::Result<()> {
        if let Some(last)=self.receipts.last().filter(|r|r.substep==6) {
            if last.solver_after!=(After{v,w})||rspeed.to_bits()!=w[1].to_bits(){return Err(bad());}
        }Ok(())
    }
}

/// Domain authority is separate from the pure physical frame. Hashes are exact
/// source/config/scene identities, not substitutes for retaining the full chain.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Context {pub battle:u64,pub slot:usize,pub session:u32,pub generation:u32,pub seq:u32,pub tick:u32,
    pub config_sha256:String,pub catalog_sha256:String,pub domain_sha256:String,pub scene_version:u32,pub scene_sha256:String}
// BW-01 wire codec (tools/bw01_wire_gen.py): Context
impl crate::bw_wire::Wire for Context {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{battle,slot,session,generation,seq,tick,config_sha256,catalog_sha256,domain_sha256,scene_version,scene_sha256}=self;W::put(battle,bw_o);W::put(slot,bw_o);W::put(session,bw_o);W::put(generation,bw_o);W::put(seq,bw_o);W::put(tick,bw_o);W::put(config_sha256,bw_o);W::put(catalog_sha256,bw_o);W::put(domain_sha256,bw_o);W::put(scene_version,bw_o);W::put(scene_sha256,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{battle:W::get(bw_i)?,slot:W::get(bw_i)?,session:W::get(bw_i)?,generation:W::get(bw_i)?,seq:W::get(bw_i)?,tick:W::get(bw_i)?,config_sha256:W::get(bw_i)?,catalog_sha256:W::get(bw_i)?,domain_sha256:W::get(bw_i)?,scene_version:W::get(bw_i)?,scene_sha256:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl Context {pub fn validate(&self)->io::Result<()> {
    let hash=|s:&str|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b));
    if self.battle==0||self.slot>=super::model::MAX_ACTORS||self.session==0||self.generation==0||!(1..=36000).contains(&self.seq)
        ||self.tick!=180+self.seq*6||self.scene_version>2048
        ||[&self.config_sha256,&self.catalog_sha256,&self.domain_sha256,&self.scene_sha256].into_iter().any(|s|!hash(s)){return Err(bad());}Ok(())
}}
#[derive(Clone,Debug,PartialEq)]
pub struct ContextFrame {pub context:Context,pub proof:Arc<FrameProof>}
// BW-01 wire codec (tools/bw01_wire_gen.py): ContextFrame
impl crate::bw_wire::Wire for ContextFrame {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{context,proof}=self;W::put(context,bw_o);W::put(proof,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{context:W::get(bw_i)?,proof:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Debug,PartialEq)]
pub struct ContactProof {pub frame:Arc<ContextFrame>,pub index:usize}
// BW-01 wire codec (tools/bw01_wire_gen.py): ContactProof
impl crate::bw_wire::Wire for ContactProof {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{frame,index}=self;W::put(frame,bw_o);W::put(index,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{frame:W::get(bw_i)?,index:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl ContactProof {pub fn receipt(&self)->io::Result<&Receipt>{self.frame.proof.receipts.get(self.index).ok_or_else(bad)}}

/// Registered by the coordinator from its verified worker, never from a frame.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Source {pub session:u32,pub generation:u32,pub config_sha256:String,pub profile:Profile}
// BW-01 wire codec (tools/bw01_wire_gen.py): Source
impl crate::bw_wire::Wire for Source {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{session,generation,config_sha256,profile}=self;W::put(session,bw_o);W::put(generation,bw_o);W::put(config_sha256,bw_o);W::put(profile,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{session:W::get(bw_i)?,generation:W::get(bw_i)?,config_sha256:W::get(bw_i)?,profile:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl Source {
    pub fn follows(&self,old:Option<&Self>)->bool {self.session!=0&&self.generation!=0
        &&self.config_sha256.len()==64&&self.config_sha256.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))
        &&old.is_none_or(|old|self==old||self.generation>old.generation)}
    pub fn matches(&self,c:&Context,p:Profile)->bool {self.session==c.session&&self.generation==c.generation
        &&self.config_sha256==c.config_sha256&&self.profile==p}
}
