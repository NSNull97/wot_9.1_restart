using JoltPhysicsSharp;

namespace MapDrive;

// Versioned test_lab steering policy. Jolt still owns drivetrain torque,
// suspension, body integration and ground contact. This class changes driver
// controls and track scrub coefficients only, never the body pose or velocity.
internal sealed class TrackedHandling
{
    private const float LateralAccelerationBudget = 3f; // Project policy, m/s^2.
    private const float OuterPivotFrictionFraction = .001f;
    private readonly float width, maximumYaw;
    private readonly WheelSettingsTV[] wheels;
    private readonly float[] lateral;
    private float yawTarget, motorInput;

    // Each track's rotating mass is an explicit 2% equivalent ring policy.
    // Native's fixed 10kgm² example inertia is retained as a lower bound;
    // using that tiny value for a 68t body produces asymmetric constraint
    // convergence. This is not an imported historical drivetrain parameter.
    public static float TrackInertia(float massKg, float radius)
    {
        if (!float.IsFinite(massKg) || massKg < 1000 || massKg > 100000 ||
            !float.IsFinite(radius) || radius < .05f || radius > 1)
            throw new InvalidDataException("tracked inertia mass/radius bounds");
        return MathF.Max(10, .02f * massKg * radius * radius);
    }

    public TrackedHandling(float trackWidth, float maxYawRate, WheelSettingsTV[] supportWheels)
    {
        if (!float.IsFinite(trackWidth) || trackWidth < .5f || trackWidth > 5 ||
            !float.IsFinite(maxYawRate) || maxYawRate < .05f || maxYawRate > 2 || supportWheels.Length != 6)
            throw new InvalidDataException("tracked handling geometry/yaw/support bounds");
        width = trackWidth; maximumYaw = maxYawRate; wheels = supportWheels;
        lateral = wheels.Select(w => w.LateralFriction).ToArray();
        if (lateral.Any(x => !float.IsFinite(x) || x < .1f || x > 2))
            throw new InvalidDataException("tracked handling lateral friction bounds");
    }

    public void VerifyWheelSettings(VehicleConstraint constraint)
    {
        if (constraint.WheelsCount != 6 || Enumerable.Range(0, 6)
            .Any(i => constraint.GetWheel(i).Settings.Handle != wheels[i].Handle))
            throw new InvalidOperationException("tracked handling wheel settings are not constraint-owned references");
    }

    public void Apply(TrackedVehicleController controller, float signedSpeed, float actualYawRate,
        int throttle, int steer, bool brake, float forwardLimit, float reverseLimit, float deltaTime)
    {
        if (!float.IsFinite(signedSpeed) || !float.IsFinite(actualYawRate) ||
            !float.IsFinite(deltaTime) || deltaTime <= 0 || deltaTime > .1f ||
            throttle < -1 || throttle > 1 || steer < -1 || steer > 1 ||
            !float.IsFinite(forwardLimit) || forwardLimit <= 0 ||
            !float.IsFinite(reverseLimit) || reverseLimit <= 0 || (brake && (throttle != 0 || steer != 0)))
            throw new InvalidDataException("tracked handling command bounds");

        float speed = MathF.Abs(signedSpeed);
        float yawLimit = MathF.Min(maximumYaw, LateralAccelerationBudget / MathF.Max(speed, .1f));
        // Reverse steering follows the former domain convention: holding the
        // same steering key while reversing changes the body's yaw sign.
        float desiredYaw = brake ? 0 : steer * (throttle < 0 ? -1 : 1) * yawLimit;
        yawTarget = Approach(yawTarget, desiredYaw, maximumYaw * 3 * deltaTime);
        if (brake) yawTarget = 0;

        // Pivot scrub occurs at fore/aft supports; retain middle support grip
        // so lowering rotational resistance does not remove all lateral grip.
        // Fore/aft scrub resists every tracked turn, including moving turns.
        // A speed-only return to full scrub created a heavy-vehicle deadlock:
        // slight forward creep restored resistance before yaw could develop.
        float pivotBlend = steer == 0 || brake ? 0 : 1;
        for (int i = 0; i < wheels.Length; i++)
        {
            float target = lateral[i] * (i % 3 == 1 ? 1 : 1 - pivotBlend * (1 - OuterPivotFrictionFraction));
            wheels[i].LateralFriction = Approach(wheels[i].LateralFriction, target, lateral[i] * 5 * deltaTime);
        }

        float left = 1, right = 1, motor = throttle;
        if (steer != 0 || MathF.Abs(yawTarget) > .001f)
        {
            if (throttle == 0)
            {
                // Equal and opposite track motion has zero requested forward
                // component. Measured yaw limits motor torque near the target.
                float sign = MathF.Sign(yawTarget);
                if (sign != 0)
                {
                    left = sign; right = -sign;
                    motor = Math.Clamp(4 * (MathF.Abs(yawTarget) - sign * actualYawRate) / maximumYaw, 0, 1);
                }
                else motor = 0;
            }
            else
            {
                // Differential track speeds v +/- yaw*width/2. Use a modest
                // launch speed only while near rest, avoiding an instantaneous
                // ratio flip as a moving forward/reverse command is engaged.
                float basisSpeed = throttle * MathF.Max(speed, maximumYaw * width);
                float correction = Math.Clamp((yawTarget - actualYawRate) * .5f, -yawLimit * .5f, yawLimit * .5f);
                float turn = Math.Clamp(yawTarget + correction, -yawLimit * 1.5f, yawLimit * 1.5f) * width / 2;
                float leftSpeed = basisSpeed + turn, rightSpeed = basisSpeed - turn;
                float divisor = MathF.Max(MathF.Abs(leftSpeed), MathF.Abs(rightSpeed));
                left = MathF.Max(.05f, throttle * leftSpeed / divisor);
                right = MathF.Max(.05f, throttle * rightSpeed / divisor);
            }
        }
        if (steer == 0 && throttle == 0) motor = 0;
        if ((throttle > 0 && signedSpeed >= forwardLimit) || (throttle < 0 && signedSpeed <= -reverseLimit)) motor = 0;
        // Braking and a released throttle never leave a queued driving torque.
        // Positive requests otherwise enter over a bounded half-second ramp.
        motorInput = brake || motor == 0 ? 0 : Approach(motorInput, motor, 2 * deltaTime);
        controller.SetDriverInput(motorInput, left, right, brake ? 1 : 0);
    }

    private static float Approach(float value, float target, float amount) =>
        value < target ? MathF.Min(value + amount, target) : MathF.Max(value - amount, target);
}
