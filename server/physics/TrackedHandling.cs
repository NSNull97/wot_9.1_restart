using JoltPhysicsSharp;

namespace MapDrive;

// Versioned test_lab steering policy. Jolt still owns drivetrain torque,
// suspension, body integration and ground contact. This class changes driver
// controls, track scrub coefficients and a bounded inner-track brake only,
// never the body pose or velocity.
internal sealed class TrackedHandling
{
    private const float LateralAccelerationBudget = 3f; // Project policy, m/s^2.
    private const float OuterPivotFrictionFraction = .001f;
    // Owner run 2026-10-14: 4% outer grip slid sideways on slopes in moving
    // turns. Low scrub stays limited to near-rest pivots.
    private const float OuterMovingFrictionFraction = .4f;
    private const float MovingGripStartSpeed = 1.5f, MovingGripFullSpeed = 4f;
    // Hysteresis: a released-throttle turn starts above 1.5 m/s and hands
    // off to the pivot below 1 m/s, so the turn does not fade near rest.
    private const float CoastEnterSpeed = 1.5f, CoastPivotSpeed = 1f;
    // Owner runs 2026-10-14: a free-rolling steer-only coast circled for more
    // than 15 s before pivoting; braking both tracks then stopped the turn
    // until rest. Jolt's shared brake locks both tracks, so a released
    // throttle brakes each track separately (clutch-brake steering): the
    // inner one harder than the outer. Targets are per-track half-mass
    // decelerations so MS-1 and IS-7 behave alike; each is capped by that
    // track's source brake torque. Project policy, m/s^2.
    private const float CoastInnerDeceleration = 8f, CoastOuterDeceleration = 2f;
    // Shared-battle test_lab policy: powered steering dissipates inner-track
    // energy at speed. Preserve launch/pivot forces through 4 m/s, then blend
    // to 2 m/s^2 at 8 m/s. These are project thresholds, not historical data.
    private const float PoweredInnerDeceleration = 2f;
    private const float PoweredBrakeStartSpeed = 4f, PoweredBrakeFullSpeed = 8f;
    // Released-throttle turns keep pivot-level scrub; the higher moving-turn
    // grip is for powered turns on slopes.
    private const float CoastOuterFrictionFraction = .001f;
    // Near-rest ratio crossing before the pivot: rate per second, minimum time.
    private const float CoastRatioRate = 20f, CoastTransitionSeconds = .1f;
    // An opposite W/S request brakes through zero instead of waiting for the
    // transmission to reverse against the existing momentum.
    private const float ReversalBrakeSpeed = .5f;
    private const float MotorRampPerSecond = 4f;
    public const float GearSwitchTime = .15f, ClutchReleaseTime = .1f, GearSwitchLatency = .2f;
    private readonly float width, maximumYaw, halfMass, radius;
    private readonly bool poweredTurnLoss;
    private readonly WheelSettingsTV[] wheels;
    private readonly float[] lateral;
    private float yawTarget, motorInput;
    // 0: ordinary drive/pivot; 1: rolling turn; 2: near-rest ratio transition.
    private int coastPhase, coastDirection;
    private float coastTransitionTime;

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

    public TrackedHandling(float trackWidth, float maxYawRate, float massKg, WheelSettingsTV[] supportWheels,
        bool enablePoweredTurnLoss = false)
    {
        if (!float.IsFinite(trackWidth) || trackWidth < .5f || trackWidth > 5 ||
            !float.IsFinite(maxYawRate) || maxYawRate < .05f || maxYawRate > 2 ||
            !float.IsFinite(massKg) || massKg < 1000 || massKg > 100000 || supportWheels.Length != 6)
            throw new InvalidDataException("tracked handling geometry/yaw/mass/support bounds");
        width = trackWidth; maximumYaw = maxYawRate; wheels = supportWheels;
        poweredTurnLoss = enablePoweredTurnLoss;
        halfMass = massKg / 2; radius = wheels[0].Radius;
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
        if (brake || throttle != 0 || steer == 0) coastPhase = 0;
        else if (speed >= CoastEnterSpeed)
        {
            coastPhase = 1;
            coastDirection = Math.Sign(signedSpeed);
        }
        else if (coastPhase == 1 && speed <= CoastPivotSpeed)
        {
            coastPhase = 2;
            coastTransitionTime = 0;
        }
        float yawLimit = MathF.Min(maximumYaw, LateralAccelerationBudget / MathF.Max(speed, .1f));
        // Diagnostic coast curvature: passive rolling must not demand the
        // powered yaw rate as momentum decays. Minimum radius is project policy.
        if (coastPhase == 1) yawLimit = MathF.Min(yawLimit, speed / (2 * width));
        // Reverse steering follows the former domain convention: holding the
        // same steering key while reversing changes the body's yaw sign.
        int travelDirection = coastPhase == 1 ? coastDirection : throttle < 0 ? -1 : 1;
        float desiredYaw = brake ? 0 : steer * travelDirection * yawLimit;
        yawTarget = Approach(yawTarget, desiredYaw, maximumYaw * 3 * deltaTime);
        if (brake) yawTarget = 0;

        // Pivot scrub occurs at fore/aft supports; retain middle support grip
        // so lowering rotational resistance does not remove all lateral grip.
        // Fore/aft scrub resists every tracked turn, including moving turns.
        // A speed-only return to full scrub created a heavy-vehicle deadlock:
        // slight forward creep restored resistance before yaw could develop.
        // On real terrain the middle supports alone can saturate even while
        // both stay grounded. Restore a limited outer-support grip at speed;
        // keep the proven low-speed scrub policy so heavy pivots can start.
        // These thresholds/coefficient are engineering policy, not 0.9.1 data.
        float movingGrip = Math.Clamp((speed - MovingGripStartSpeed) /
            (MovingGripFullSpeed - MovingGripStartSpeed), 0, 1);
        float outerFraction = coastPhase == 1 ? CoastOuterFrictionFraction : OuterPivotFrictionFraction +
            movingGrip * (OuterMovingFrictionFraction - OuterPivotFrictionFraction);
        float pivotBlend = steer == 0 || brake ? 0 : 1;
        for (int i = 0; i < wheels.Length; i++)
        {
            float target = lateral[i] * (i % 3 == 1 ? 1 : 1 - pivotBlend * (1 - outerFraction));
            wheels[i].LateralFriction = Approach(wheels[i].LateralFriction, target, lateral[i] * 5 * deltaTime);
        }

        float left = 1, right = 1, motor = throttle;
        if (coastPhase == 2)
        {
            // Only cross a track ratio through zero after measured near rest.
            // A full +1 -> -1 change takes at least .1s with no engine request;
            // the next ordinary pivot still enters through the motor ramp.
            left = NonzeroRatio(Approach(controller.LeftRatio, steer, CoastRatioRate * deltaTime), steer);
            right = NonzeroRatio(Approach(controller.RightRatio, -steer, CoastRatioRate * deltaTime), -steer);
            motor = 0;
            coastTransitionTime += deltaTime;
            // Reverse coast initially has the opposite yaw target. Do not
            // hand off until its slew agrees with these pivot ratios, or the
            // ordinary branch would flip them back for a few substeps.
            if (coastTransitionTime >= CoastTransitionSeconds && left == steer && right == -steer &&
                yawTarget * steer > .001f) coastPhase = 0;
        }
        else if (steer != 0 || (throttle != 0 && MathF.Abs(yawTarget) > .001f))
        {
            if (throttle == 0 && coastPhase == 0)
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
                // A rolling steering-only request uses the same differential
                // geometry, but offers no engine torque. Track/contact forces
                // steer the existing momentum; they do not request a stop.
                int ratioDirection = coastPhase == 1 ? coastDirection : throttle;
                float basisSpeed = ratioDirection * MathF.Max(speed, maximumYaw * width);
                float correction = Math.Clamp((yawTarget - actualYawRate) * .5f, -yawLimit * .5f, yawLimit * .5f);
                float turn = Math.Clamp(yawTarget + correction, -yawLimit * 1.5f, yawLimit * 1.5f) * width / 2;
                float leftSpeed = basisSpeed + turn, rightSpeed = basisSpeed - turn;
                float divisor = MathF.Max(MathF.Abs(leftSpeed), MathF.Abs(rightSpeed));
                left = MathF.Max(.05f, ratioDirection * leftSpeed / divisor);
                right = MathF.Max(.05f, ratioDirection * rightSpeed / divisor);
            }
        }
        if (steer == 0 && throttle == 0) motor = 0;
        if ((throttle > 0 && signedSpeed >= forwardLimit) || (throttle < 0 && signedSpeed <= -reverseLimit)) motor = 0;
        float brakeInput = brake ? 1 : 0;
        if (coastPhase == 1)
        {
            // Bounded by the inner track's own brake torque and never past
            // zero: this can only dissipate track speed, not add energy.
            var inner = steer > 0 ? controller.RightTrack : controller.LeftTrack;
            var outer = steer > 0 ? controller.LeftTrack : controller.RightTrack;
            Dissipate(inner, TrackBrake(inner, CoastInnerDeceleration, deltaTime));
            Dissipate(outer, TrackBrake(outer, CoastOuterDeceleration, deltaTime));
        }
        if (throttle != 0 && throttle * signedSpeed < -ReversalBrakeSpeed)
        {
            motor = 0;
            brakeInput = 1;
        }
        if (poweredTurnLoss && !brake && coastPhase == 0 && throttle != 0 && steer != 0 &&
            motor != 0 && brakeInput == 0 && throttle * signedSpeed > PoweredBrakeStartSpeed)
        {
            var inner = steer > 0 ? controller.RightTrack : controller.LeftTrack;
            float speedBlend = Math.Clamp((speed - PoweredBrakeStartSpeed) /
                (PoweredBrakeFullSpeed - PoweredBrakeStartSpeed), 0, 1);
            float yawFraction = Math.Clamp(MathF.Abs(yawTarget) / maximumYaw, 0, 1);
            Dissipate(inner, TrackBrake(inner, PoweredInnerDeceleration * speedBlend * yawFraction, deltaTime));
        }
        // A direction change cancels the old request immediately. Ramping
        // through zero would keep driving the wrong way for half a second.
        // The new request still ramps from rest after the reversal brake.
        if (motorInput * motor < 0) motorInput = 0;
        // Braking and a released throttle never leave a queued driving torque.
        // Nonzero requests otherwise enter over a bounded quarter-second ramp.
        motorInput = brakeInput > 0 || motor == 0 ? 0 : Approach(motorInput, motor, MotorRampPerSecond * deltaTime);
        controller.SetDriverInput(motorInput, left, right, brakeInput);
    }

    // Track speed change for a retarding force halfMass*deceleration at the
    // track radius, never more than the track's own brake torque allows.
    private float TrackBrake(VehicleTrack track, float deceleration, float deltaTime) =>
        MathF.Min(halfMass * deceleration * radius, track.MaxBrakeTorque) * deltaTime / track.Inertia;

    private static void Dissipate(VehicleTrack track, float limit)
    {
        float w = track.AngularVelocity;
        track.AngularVelocity = w - MathF.Sign(w) * MathF.Min(MathF.Abs(w), limit);
    }

    private static float Approach(float value, float target, float amount) =>
        value < target ? MathF.Min(value + amount, target) : MathF.Max(value - amount, target);

    private static float NonzeroRatio(float value, int targetSign) =>
        MathF.Abs(value) >= .05f ? value : .05f * (value == 0 ? targetSign : MathF.Sign(value));
}
