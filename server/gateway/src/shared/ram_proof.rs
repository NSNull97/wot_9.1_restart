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
pub enum Profile { Ms1, Is7 }
impl Profile {
    pub fn sha(self)->&'static str { match self {
        Self::Ms1=>"48f8ac675afafbe8605bd97bd92dc2c37f26673b65a548d4f0402b815f7ee9a1",
        Self::Is7=>"2b72923c904678b5471ca4c8e01125f787d0baeb8cf2153c322a126fa1b6cfd7" } }
    pub fn mass(self)->f32 {match self{Self::Ms1=>4691.,Self::Is7=>68190.}}
    pub fn half(self)->[f32;3] {match self{Self::Ms1=>[0x3f51f106,0x3f14c187,0x400061e9],
        Self::Is7=>[0x3fd295e4,0x3f0b3f54,0x4066fa42]}.map(f32::from_bits)}
    pub fn binding(self)->BodyBinding {
        let (u,p)=match self{Self::Ms1=>(0x395f8781,[0x390ec909,0x3919bf9b,0x3a25f4bb]),
            Self::Is7=>(0x3776094c,[0x363bac7f,0x365da392,0x3775d3e2])};
        BodyBinding{inverse_mass:f32::from_bits(u),principal:p.map(f32::from_bits),
            inertia_rotation:[0x3f3504f3,0x3f3504f3,0,0].map(f32::from_bits)}
    }
    fn lever(self,p:[f32;3],com:[f32;3])->bool {
        let h=self.half().map(f64::from);let r=std::array::from_fn::<_,3,_>(|i|f64::from(p[i])-f64::from(com[i]));
        (r[0]*r[0]+r[1]*r[1])+r[2]*r[2] <= 4.*((h[0]*h[0]+h[1]*h[1])+h[2]*h[2])
    }
}
#[derive(Clone,Copy,Debug)]
pub struct BodyBinding {pub inverse_mass:f32,pub principal:[f32;3],pub inertia_rotation:[f32;4]}
impl PartialEq for BodyBinding {fn eq(&self,b:&Self)->bool {self.inverse_mass.to_bits()==b.inverse_mass.to_bits()
    &&bits(self.principal,b.principal)&&bits(self.inertia_rotation,b.inertia_rotation)}}
#[derive(Clone,Copy,Debug)]
pub struct After {pub v:[f32;3],pub w:[f32;3]}
impl PartialEq for After {fn eq(&self,b:&Self)->bool{bits(self.v,b.v)&&bits(self.w,b.w)}}
impl After {fn valid(self)->bool {self.v.iter().chain(&self.w).all(|v|v.is_finite())
    &&dot(self.v,self.v)<=625.&&self.w.iter().all(|v|v.abs()<=20.)}}
#[derive(Clone,Copy,Debug)]
pub struct FullMotion {pub com:[f32;3],pub rotation:[f32;4],pub motion:After,pub inertia:[f32;9]}
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
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Mode {Normal,Total,Angular}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum SolverBranch {Applied,Nonclosing,Quantized}
#[derive(Clone,Copy,Debug)]
pub struct Geometry {pub point:[f32;3],pub normal:[f32;3]}
impl PartialEq for Geometry {fn eq(&self,b:&Self)->bool{bits(self.point,b.point)&&bits(self.normal,b.normal)}}
impl Geometry {pub fn scalar(self)->Contact{Contact{point:self.point,normal:self.normal}}
    fn valid(self)->bool {self.point.iter().chain(&self.normal).all(|v|v.is_finite())
        &&self.point.iter().all(|v|v.abs()<=2000.)&&self.normal.iter().all(|v|v.abs()<=1.)
        &&(dot(self.normal,self.normal)-1.).abs()<=0.0001}}
#[derive(Clone,Debug,PartialEq)]
pub struct Receipt {pub object_id:u32,pub substep:u8,pub order:u8,pub geometry:Geometry,pub mode:Mode,
    pub budget_after:After,pub solver_after:After,pub energy_j:u32,
    pub legacy:Option<Geometry>,pub solver_branch:Option<SolverBranch>}
#[derive(Clone,Debug,PartialEq)]
pub struct FrameProof {pub profile:Profile,pub binding:BodyBinding,pub witnesses:Vec<Witness>,pub receipts:Vec<Receipt>}
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
impl Context {pub fn validate(&self)->io::Result<()> {
    let hash=|s:&str|s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b));
    if self.battle==0||self.slot>=super::model::MAX_ACTORS||self.session==0||self.generation==0||!(1..=36000).contains(&self.seq)
        ||self.tick!=180+self.seq*6||self.scene_version>2048
        ||[&self.config_sha256,&self.catalog_sha256,&self.domain_sha256,&self.scene_sha256].into_iter().any(|s|!hash(s)){return Err(bad());}Ok(())
}}
#[derive(Clone,Debug,PartialEq)]
pub struct ContextFrame {pub context:Context,pub proof:Arc<FrameProof>}
#[derive(Clone,Debug,PartialEq)]
pub struct ContactProof {pub frame:Arc<ContextFrame>,pub index:usize}
impl ContactProof {pub fn receipt(&self)->io::Result<&Receipt>{self.frame.proof.receipts.get(self.index).ok_or_else(bad)}}

/// Registered by the coordinator from its verified worker, never from a frame.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Source {pub session:u32,pub generation:u32,pub config_sha256:String,pub profile:Profile}
impl Source {
    pub fn follows(&self,old:Option<&Self>)->bool {self.session!=0&&self.generation!=0
        &&self.config_sha256.len()==64&&self.config_sha256.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))
        &&old.is_none_or(|old|self==old||self.generation>old.generation)}
    pub fn matches(&self,c:&Context,p:Profile)->bool {self.session==c.session&&self.generation==c.generation
        &&self.config_sha256==c.config_sha256&&self.profile==p}
}
