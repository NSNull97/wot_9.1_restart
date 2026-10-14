//! Stage-A scalar kernel only. Not wired into worker, domain or runtime.
//! Exact f32 inputs are promoted once; scalar f64 order matches the frozen
//! C# component contract. No FMA, Vector3, velocity injection or source claims.

pub const ENERGY_J: f64 = 8000.0;
pub const PAID_TOLERANCE_J: f64 = 0.125;
const EPS32: f64 = 1.0 / 8_388_608.0;
type D3 = [f64; 3];
type M3 = [[f64; 3]; 3];

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Motion {
    pub com: [f32; 3],
    pub velocity: [f32; 3],
    pub omega: [f32; 3],
    pub inverse_mass: f32,
    /// Raw native world inverse inertia, all nine f32 components.
    pub inverse_inertia: [[f32; 3]; 3],
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Contact { pub point: [f32; 3], pub normal: [f32; 3] }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Error { Bounds, Normal, Asymmetry, NonSpd, NonFinite }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Branch {
    ShadowApplied, ShadowIneligible, ShadowQuantized,
    Applied, NoopNonclosing, NoopZero, NoopQuantized,
}
impl Branch {
    pub fn name(self) -> &'static str { match self {
        Self::ShadowApplied => "shadow_applied", Self::ShadowIneligible => "shadow_ineligible",
        Self::ShadowQuantized => "shadow_quantized", Self::Applied => "applied",
        Self::NoopNonclosing => "noop_nonclosing", Self::NoopZero => "noop_zero",
        Self::NoopQuantized => "noop_quantized",
    } }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Measurement {
    pub closing: f64,
    pub rotational_closing: f64,
    pub inverse_effective_mass: f64,
    pub normal_energy: f64,
    pub body_energy: f64,
}
impl Measurement {
    pub fn eligible(self) -> bool {
        self.closing >= 0.1 && self.rotational_closing > 0.0 && self.normal_energy >= ENERGY_J
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Response {
    pub branch: Branch,
    pub velocity: [f32; 3],
    pub omega: [f32; 3],
    pub before: Measurement,
    pub after: Measurement,
    pub requested_loss: f64,
    pub actual_loss: f64,
    pub candidate_loss: f64,
    pub impulse: f64,
}

fn d(v: [f32; 3]) -> D3 { v.map(f64::from) }
fn dot(a: D3, b: D3) -> f64 { (a[0]*b[0] + a[1]*b[1]) + a[2]*b[2] }
fn cross(a: D3, b: D3) -> D3 {
    [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
}
fn mv(a: M3, v: D3) -> D3 { a.map(|row| dot(row,v)) }
fn transpose(a:M3)->M3 {std::array::from_fn(|i|std::array::from_fn(|j|a[j][i]))}
fn mm(a:M3,b:M3)->M3 {let bt=transpose(b);a.map(|row|bt.map(|col|dot(row,col)))}
fn rotation(q:[f32;4])->Result<M3,Error> {
    let [x,y,z,w]=q.map(f64::from);
    let norm=((x*x+y*y)+z*z)+w*w;
    if !norm.is_finite() || (norm-1.0).abs()>=0.0001 {return Err(Error::Bounds);}
    Ok([[1.0-2.0*(y*y+z*z),2.0*(x*y-z*w),2.0*(x*z+y*w)],
        [2.0*(x*y+z*w),1.0-2.0*(x*x+z*z),2.0*(y*z-x*w)],
        [2.0*(x*z-y*w),2.0*(y*z+x*w),1.0-2.0*(x*x+y*y)]])
}
fn inverse(a: M3) -> Result<M3, Error> {
    let cof=[cross(a[1],a[2]),cross(a[2],a[0]),cross(a[0],a[1])];
    let det=dot(a[0],cof[0]);
    if a[0][0] <= 0.0 || a[0][0]*a[1][1]-a[0][1]*a[1][0] <= 0.0 || det <= 0.0 {
        return Err(Error::NonSpd);
    }
    let result:M3=std::array::from_fn(|i|std::array::from_fn(|j|cof[j][i]/det));
    if !det.is_finite() || result.iter().flatten().any(|x|!x.is_finite()) { return Err(Error::NonFinite); }
    Ok(result)
}
fn motion_bounds(v: [f32;3], w: [f32;3]) -> bool {
    v.iter().chain(&w).all(|x|x.is_finite()) && dot(d(v),d(v)) <= 625.0
        && w.iter().all(|x|x.abs() <= 20.0)
}

#[derive(Clone, Copy)]
struct Kernel { arm:D3, normal:D3, a:M3, inertia:M3, inverse_mass:f64 }
impl Kernel {
    fn checked(m: Motion, c: Contact) -> Result<Self, Error> {
        if m.com.iter().chain(&m.velocity).chain(&m.omega).chain(&c.point).chain(&c.normal)
            .chain(m.inverse_inertia.iter().flatten()).chain(std::iter::once(&m.inverse_mass))
            .any(|x|!x.is_finite()) { return Err(Error::NonFinite); }
        if m.com.iter().chain(&c.point).any(|x|x.abs()>2000.0) || !motion_bounds(m.velocity,m.omega)
            || m.inverse_mass < (1.0f32/100000.0f32) || m.inverse_mass > (1.0f32/1000.0f32)
            || m.inverse_inertia.iter().flatten().any(|x|x.abs()>1.0) { return Err(Error::Bounds); }
        let n=d(c.normal);let len=dot(n,n).sqrt();
        if n.iter().any(|x|x.abs()>2.0) || !(0.999..=1.001).contains(&len) { return Err(Error::Normal); }
        let maximum=m.inverse_inertia.iter().flatten().fold(0.0f64,|max,x|max.max(f64::from(*x).abs()));
        let tolerance=1e-12+(8.0*EPS32)*maximum;
        for i in 0..3 { for j in 0..3 {
            if (f64::from(m.inverse_inertia[i][j])-f64::from(m.inverse_inertia[j][i])).abs()>tolerance {
                return Err(Error::Asymmetry);
            }
        } }
        let a=std::array::from_fn(|i|std::array::from_fn(|j|
            (f64::from(m.inverse_inertia[i][j])+f64::from(m.inverse_inertia[j][i]))*0.5));
        let inertia=inverse(a)?;
        Ok(Self {arm:std::array::from_fn(|i|f64::from(c.point[i])-f64::from(m.com[i])),
            normal:n.map(|x|x/len),a,inertia,inverse_mass:f64::from(m.inverse_mass)})
    }
    fn measure(self,v: [f32;3],w: [f32;3]) -> Result<Measurement,Error> {
        let v=d(v);let w=d(w);let rot=cross(w,self.arm);
        let closing=dot(std::array::from_fn(|i|v[i]+rot[i]),self.normal);
        let rotational_closing=dot(rot,self.normal);
        let h=cross(self.arm,self.normal);
        let inverse_effective_mass=self.inverse_mass+dot(h,mv(self.a,h));
        let positive=closing.max(0.0);
        let normal_energy=(positive*positive)/(2.0*inverse_effective_mass);
        let linear=(0.5/self.inverse_mass)*dot(v,v);
        let angular=0.5*dot(w,mv(self.inertia,w));
        let body_energy=linear+angular;
        if inverse_effective_mass<=0.0 || [closing,rotational_closing,inverse_effective_mass,normal_energy,body_energy]
            .iter().any(|x|!x.is_finite()) || body_energy<0.0 { return Err(Error::NonFinite); }
        Ok(Measurement{closing,rotational_closing,inverse_effective_mass,normal_energy,body_energy})
    }
    fn candidate(self,m:Motion,before:Measurement,e:f64) -> Result<([f32;3],[f32;3],Measurement,f64),Error> {
        if e==0.0 { return Ok((m.velocity,m.omega,before,0.0)); }
        let root=(before.closing*before.closing-(2.0*before.inverse_effective_mass)*e).max(0.0).sqrt();
        let j=(2.0*e)/(before.closing+root);
        let h=cross(self.arm,self.normal);let ah=mv(self.a,h);let uj=self.inverse_mass*j;
        let v=std::array::from_fn(|i|(f64::from(m.velocity[i])-uj*self.normal[i]) as f32);
        let w=std::array::from_fn(|i|(f64::from(m.omega[i])-j*ah[i]) as f32);
        let after=self.measure(v,w)?;
        Ok((v,w,after,j))
    }
}

pub fn inspect(m:Motion,c:Contact) -> Result<Measurement,Error> {
    Kernel::checked(m,c)?.measure(m.velocity,m.omega)
}
/// Recorded-frame consistency only. Source/profile authority is deliberately
/// absent in Stage A and must be established by a separate immutable binding.
pub fn verify_basis(m:Motion,body_rotation:[f32;4],principal:[f32;3],inertia_rotation:[f32;4]) -> Result<(),Error> {
    Kernel::checked(m,Contact{point:m.com,normal:[1.0,0.0,0.0]})?;
    if principal.iter().any(|x|!x.is_finite() || *x<=0.0 || *x>1.0) {return Err(Error::Bounds);}
    let r=mm(rotation(body_rotation)?,rotation(inertia_rotation)?);
    let diagonal=[[f64::from(principal[0]),0.0,0.0],[0.0,f64::from(principal[1]),0.0],[0.0,0.0,f64::from(principal[2])]];
    let expected=mm(mm(r,diagonal),transpose(r));
    let maximum=m.inverse_inertia.iter().flatten().fold(0.0f64,|v,x|v.max(f64::from(*x).abs()));
    let tolerance=1e-12+(16.0*EPS32)*maximum;
    for i in 0..3 {for j in 0..3 {
        if (f64::from(m.inverse_inertia[i][j])-expected[i][j]).abs()>tolerance {return Err(Error::Bounds);}
    }}
    Ok(())
}
fn unchanged(m:Motion,before:Measurement,branch:Branch,requested_loss:f64) -> Response {
    Response{branch,velocity:m.velocity,omega:m.omega,before,after:before,
        requested_loss,actual_loss:0.0,candidate_loss:0.0,impulse:0.0}
}
fn accepted(v:[f32;3],w:[f32;3],before:Measurement,after:Measurement,e:f64) -> bool {
    let loss=before.body_energy-after.body_energy;
    motion_bounds(v,w) && loss>=0.0 && (loss-e).abs()<=PAID_TOLERANCE_J && after.closing>=0.0
}

/// Operates on one remaining shadow. Caller must separately require raw PRE
/// eligibility and legacy-linear-first failure; this helper does not pick modes.
pub fn shadow(m:Motion,c:Contact) -> Result<Response,Error> {
    let k=Kernel::checked(m,c)?;let before=k.measure(m.velocity,m.omega)?;
    if !before.eligible() { return Ok(unchanged(m,before,Branch::ShadowIneligible,0.0)); }
    let (v,w,after,j)=k.candidate(m,before,ENERGY_J)?;
    if !accepted(v,w,before,after,ENERGY_J) {
        return Ok(Response{candidate_loss:before.body_energy-after.body_energy,
            ..unchanged(m,before,Branch::ShadowQuantized,ENERGY_J)});
    }
    Ok(Response{branch:Branch::ShadowApplied,velocity:v,omega:w,before,after,
        requested_loss:ENERGY_J,actual_loss:before.body_energy-after.body_energy,
        candidate_loss:before.body_energy-after.body_energy,impulse:j})
}

/// Conservative post-solver debit. No old motion restoration and no retries.
pub fn post_solver(m:Motion,c:Contact) -> Result<Response,Error> {
    let k=Kernel::checked(m,c)?;let before=k.measure(m.velocity,m.omega)?;
    if before.closing<=0.0 {
        return Ok(unchanged(m,before,Branch::NoopNonclosing,0.0));
    }
    let e=ENERGY_J.min(before.normal_energy);
    if e==0.0 {return Ok(unchanged(m,before,Branch::NoopZero,0.0));}
    let (v,w,after,j)=k.candidate(m,before,e)?;
    if !accepted(v,w,before,after,e) {
        return Ok(Response{candidate_loss:before.body_energy-after.body_energy,
            ..unchanged(m,before,Branch::NoopQuantized,e)});
    }
    Ok(Response{branch:Branch::Applied,velocity:v,omega:w,before,after,
        requested_loss:e,actual_loss:before.body_energy-after.body_energy,
        candidate_loss:before.body_energy-after.body_energy,impulse:j})
}

#[cfg(test)]
mod tests {
    use super::*;
    fn motion() -> Motion { Motion {com:[0.;3],velocity:[0.;3],omega:[0.,-8.,0.],
        inverse_mass:0.001,inverse_inertia:[[0.001,0.,0.],[0.,0.001,0.],[0.,0.,0.001]]} }
    fn contact() -> Contact {Contact{point:[1.,0.,0.],normal:[0.,0.,1.]}}
    #[test]fn rotating_corner_applies_and_pays_with_analytic_oracle() {
        let m=motion();let out=shadow(m,contact()).unwrap();assert_eq!(out.branch,Branch::ShadowApplied);
        // Analytic equal translational/rotational mobility, independently
        // solved final normal speed sqrt(c²-4*u*8000).
        let u=f64::from(m.inverse_mass);let expected_closing=(64.-4.*u*8000.).sqrt();
        assert!((out.after.closing-expected_closing).abs()<1e-6);
        assert!((out.actual_loss-8000.).abs()<=0.125);assert!(out.after.body_energy<out.before.body_energy);
        assert!(out.velocity[2]<0.&&out.omega[1]>-8.);
    }
    #[test]fn stationary_separating_and_unrelated_axis_have_no_angular_admission() {
        for w in [[0.;3],[0.,8.,0.],[8.,0.,0.],[0.,0.,8.]] {
            let m=Motion{omega:w,..motion()};let r=shadow(m,contact()).unwrap();
            assert_eq!(r.branch,Branch::ShadowIneligible);assert_eq!(r.omega,m.omega);assert_eq!(r.velocity,m.velocity);
        }
    }
    #[test]fn stopped_post_keeps_actual_zero_not_pre_motion() {
        let m=Motion{omega:[0.;3],..motion()};let r=post_solver(m,contact()).unwrap();
        assert_eq!(r.branch,Branch::NoopNonclosing);assert_eq!(r.actual_loss,0.);assert_eq!(r.velocity,[0.;3]);
        let m=Motion{omega:[0.,1.,0.],..m};let r=post_solver(m,contact()).unwrap();
        assert_eq!(r.branch,Branch::NoopNonclosing);assert_eq!(r.omega,m.omega);
    }
    #[test]fn malformed_and_non_spd_inputs_rejected() {
        let base=motion();
        for m in [Motion{inverse_mass:f32::NAN,..base},Motion{velocity:[26.,0.,0.],..base},
            Motion{omega:[0.,21.,0.],..base},Motion{com:[2001.,0.,0.],..base},
            Motion{inverse_inertia:[[0.;3];3],..base},
            Motion{inverse_inertia:[[0.001,0.001,0.],[0.,0.001,0.],[0.,0.,0.001]],..base}] {
            assert!(shadow(m,contact()).is_err());assert!(post_solver(m,contact()).is_err());
        }
        assert_eq!(inspect(base,Contact{normal:[0.;3],..contact()}),Err(Error::Normal));
    }
    #[test]fn shared_spin_budget_is_not_recreated_per_object() {
        let mut m=motion();let mut count=0;
        for _ in 0..4 {let r=shadow(m,contact()).unwrap();if r.branch==Branch::ShadowApplied {
            count+=1;m.velocity=r.velocity;m.omega=r.omega;
        }}
        assert!(count>0&&count<=2);assert_eq!(shadow(m,contact()).unwrap().branch,Branch::ShadowIneligible);
    }
}
