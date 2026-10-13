using System.Numerics;

namespace MapDrive;

// Pure scalar kernel, frozen by the Stage-A cross-language witnesses. Native
// callback/body/catalog integration is owned by AngularFractureResponse.
// Explicit project impulse/rounding policy, not a recovered historical solver.
internal static class AngularContactResponse
{
    public const double ReservationJ = 8000, AccountingToleranceJ = .125;
    const double FloatEpsilon = 1.0 / 8388608;
    public readonly record struct Motion(Vector3 Linear, Vector3 Angular);
    public readonly record struct Inspection(double Closing, double RotationalClosing,
        double NormalEnergy, double BodyEnergy, bool Eligible);
    public readonly record struct Result(string Branch, Motion Output, Inspection Before,
        double RequestedEnergy, double ActualLoss, double CandidateLoss, double ClosingAfter);

    readonly record struct D3(double X, double Y, double Z)
    {
        public D3(Vector3 v) : this(v.X, v.Y, v.Z) { }
        public static D3 operator +(D3 a, D3 b) => new(a.X+b.X,a.Y+b.Y,a.Z+b.Z);
        public static D3 operator -(D3 a, D3 b) => new(a.X-b.X,a.Y-b.Y,a.Z-b.Z);
        public static D3 operator *(double k,D3 v) => new(k*v.X,k*v.Y,k*v.Z);
        public static D3 operator /(D3 v,double k) => new(v.X/k,v.Y/k,v.Z/k);
        public Vector3 F32() => new((float)X,(float)Y,(float)Z);
        public double At(int i) => i==0?X:i==1?Y:Z;
    }
    readonly record struct M3(D3 A,D3 B,D3 C)
    {
        public D3 Row(int i) => i==0?A:i==1?B:C;
        public double At(int i,int j) => Row(i).At(j);
        public M3 Transpose() => new(new(A.X,B.X,C.X),new(A.Y,B.Y,C.Y),new(A.Z,B.Z,C.Z));
        public D3 Times(D3 v) => new(Dot(A,v),Dot(B,v),Dot(C,v));
        public M3 Times(M3 m)
        {
            var t=m.Transpose();
            return new(new(Dot(A,t.A),Dot(A,t.B),Dot(A,t.C)),
                new(Dot(B,t.A),Dot(B,t.B),Dot(B,t.C)),new(Dot(C,t.A),Dot(C,t.B),Dot(C,t.C)));
        }
        public double Determinant() => Dot(A,Cross(B,C));
        public M3 Inverse()
        {
            var t=new M3(Cross(B,C),Cross(C,A),Cross(A,B)).Transpose();
            double det=Determinant();return new(t.A/det,t.B/det,t.C/det);
        }
    }
    static double Dot(D3 a,D3 b) => (a.X*b.X+a.Y*b.Y)+a.Z*b.Z;
    static D3 Cross(D3 a,D3 b) => new(a.Y*b.Z-a.Z*b.Y,a.Z*b.X-a.X*b.Z,a.X*b.Y-a.Y*b.X);
    static void Require(bool ok,string reason) { if(!ok)throw new ArgumentException(reason); }
    static bool Bounded(Vector3 v,double b) => float.IsFinite(v.X)&&float.IsFinite(v.Y)&&float.IsFinite(v.Z)
        &&Math.Abs((double)v.X)<=b&&Math.Abs((double)v.Y)<=b&&Math.Abs((double)v.Z)<=b;
    static bool MotionBounded(Motion m) => Bounded(m.Linear,25)&&Dot(new(m.Linear),new(m.Linear))<=625&&Bounded(m.Angular,20);

    public sealed class Frame
    {
        readonly D3 com;
        readonly double inverseMass;
        readonly M3 raw, inverseInertia, inertia;
        readonly double maximum;
        public Frame(Vector3 centerOfMass,float inverseMassValue,IReadOnlyList<float> rawNativeInverseInertia)
        {
            Require(Bounded(centerOfMass,2000),"COM bound");
            Require(float.IsFinite(inverseMassValue)&&inverseMassValue>=(float)(1d/100000)
                &&inverseMassValue<=(float)(1d/1000),"inverse mass bound");
            Require(rawNativeInverseInertia.Count==9,"matrix size");
            foreach(float x in rawNativeInverseInertia)Require(float.IsFinite(x)&&Math.Abs((double)x)<=1,"matrix bound");
            com=new(centerOfMass);inverseMass=inverseMassValue;
            raw=new(new(rawNativeInverseInertia[0],rawNativeInverseInertia[1],rawNativeInverseInertia[2]),
                new(rawNativeInverseInertia[3],rawNativeInverseInertia[4],rawNativeInverseInertia[5]),
                new(rawNativeInverseInertia[6],rawNativeInverseInertia[7],rawNativeInverseInertia[8]));
            maximum=0;for(int i=0;i<3;i++)for(int j=0;j<3;j++)maximum=Math.Max(maximum,Math.Abs(raw.At(i,j)));
            for(int i=0;i<3;i++)for(int j=0;j<3;j++)
                Require(Math.Abs(raw.At(i,j)-raw.At(j,i))<=1e-12+8*FloatEpsilon*maximum,"matrix asymmetry");
            double s(int i,int j)=>(raw.At(i,j)+raw.At(j,i))*.5;
            inverseInertia=new(new(s(0,0),s(0,1),s(0,2)),new(s(1,0),s(1,1),s(1,2)),new(s(2,0),s(2,1),s(2,2)));
            Require(inverseInertia.A.X>0&&inverseInertia.A.X*inverseInertia.B.Y-inverseInertia.A.Y*inverseInertia.B.X>0
                &&inverseInertia.Determinant()>0,"matrix SPD");
            inertia=inverseInertia.Inverse();
            for(int i=0;i<3;i++)for(int j=0;j<3;j++)Require(double.IsFinite(inertia.At(i,j)),"inverse finite");
        }
        // Tensor frame math alone cannot authorize a source profile. The caller
        // separately verifies the complete AngularBodyBinding lookup/getters.
        public void VerifyBasis(Quaternion bodyRotation,Vector3 principalInverse,Quaternion inertiaRotation)
        {
            Require(Bounded(principalInverse,1)&&principalInverse.X>0&&principalInverse.Y>0&&principalInverse.Z>0,"principal bound");
            var rotation=Rotation(bodyRotation).Times(Rotation(inertiaRotation));
            var diagonal=new M3(new(principalInverse.X,0,0),new(0,principalInverse.Y,0),new(0,0,principalInverse.Z));
            var expected=rotation.Times(diagonal).Times(rotation.Transpose());
            for(int i=0;i<3;i++)for(int j=0;j<3;j++)
                Require(Math.Abs(raw.At(i,j)-expected.At(i,j))<=1e-12+16*FloatEpsilon*maximum,"tensor frame mismatch");
        }
        static M3 Rotation(Quaternion q)
        {
            double x=q.X,y=q.Y,z=q.Z,w=q.W;
            double norm=((x*x+y*y)+z*z)+w*w;
            Require(double.IsFinite(norm)&&Math.Abs(norm-1)<.0001,"quaternion bound");
            return new(new(1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)),
                new(2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)),new(2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)));
        }
        double Energy(Motion m) => (.5/inverseMass)*Dot(new D3(m.Linear),new D3(m.Linear))+.5*Dot(new D3(m.Angular),inertia.Times(new D3(m.Angular)));
        (D3 Normal,D3 Arm,D3 H,double D) Geometry(Vector3 point,Vector3 reportedNormal)
        {
            Require(Bounded(point,2000)&&Bounded(reportedNormal,2),"contact bound");
            var normal=new D3(reportedNormal);double length=Math.Sqrt(Dot(normal,normal));
            Require(length>=.999&&length<=1.001,"normal length");normal/=length;
            var arm=new D3(point)-com;var h=Cross(arm,normal);double d=inverseMass+Dot(h,inverseInertia.Times(h));
            Require(double.IsFinite(d)&&d>0,"effective inverse mass");return(normal,arm,h,d);
        }
        Inspection Evaluate(Motion motion,(D3 Normal,D3 Arm,D3 H,double D) g)
        {
            var rotation=Cross(new(motion.Angular),g.Arm);
            double c=Dot(new D3(motion.Linear)+rotation,g.Normal),rot=Dot(rotation,g.Normal),closing=Math.Max(0,c);
            double energy=(closing*closing)/(2*g.D),bodyEnergy=Energy(motion);
            Require(double.IsFinite(c)&&double.IsFinite(rot)&&double.IsFinite(energy)&&double.IsFinite(bodyEnergy)&&bodyEnergy>=0,"energy finite");
            return new(c,rot,energy,bodyEnergy,c>=.1&&rot>0&&energy>=ReservationJ);
        }
        public Inspection Inspect(Motion motion,Vector3 point,Vector3 reportedNormal)
        {
            Require(MotionBounded(motion),"input motion bound");return Evaluate(motion,Geometry(point,reportedNormal));
        }
        public Result Shadow(Motion motion,Vector3 point,Vector3 reportedNormal) => Apply(motion,point,reportedNormal,true);
        public Result Post(Motion motion,Vector3 point,Vector3 reportedNormal) => Apply(motion,point,reportedNormal,false);
        Result Apply(Motion input,Vector3 point,Vector3 reportedNormal,bool shadow)
        {
            Require(MotionBounded(input),"input motion bound");var g=Geometry(point,reportedNormal);var before=Evaluate(input,g);
            Result Unchanged(string branch,double request=0,double candidateLoss=0)=>new(branch,input,before,request,0,candidateLoss,before.Closing);
            if(shadow&&!before.Eligible)return Unchanged("shadow_ineligible");
            if(!shadow&&before.Closing<=0)return Unchanged("noop_nonclosing");
            double e=shadow?ReservationJ:Math.Min(ReservationJ,before.NormalEnergy);
            if(e==0)return Unchanged("noop_zero");
            double radicand=Math.Max(0,before.Closing*before.Closing-(2*g.D)*e);
            double impulse=(2*e)/(before.Closing+Math.Sqrt(radicand));
            var output=new Motion((new D3(input.Linear)-(inverseMass*impulse)*g.Normal).F32(),
                (new D3(input.Angular)-impulse*inverseInertia.Times(g.H)).F32());
            // Evaluate the once-rounded pair; no clipping, retry or PRE refund.
            var after=Evaluate(output,g);double loss=before.BodyEnergy-after.BodyEnergy;
            if(!MotionBounded(output)||loss<0||Math.Abs(loss-e)>AccountingToleranceJ||after.Closing<0)
                return Unchanged(shadow?"shadow_quantized":"noop_quantized",e,loss);
            return new(shadow?"shadow_applied":"applied",output,before,e,loss,loss,after.Closing);
        }
    }
}
