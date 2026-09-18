/* SPDX-License-Identifier: MIT */
/* Copyright (c) 2026 Andrew de Quincey */

/*
 * stepper.h - open-loop step generation for the two RAMPS axes.
 *
 * Each axis has its own 16-bit timer, so both can move at the same time at
 * independent rates without interfering. Timer1 drives X, Timer3 drives Y.
 * Moves run at a constant step rate with no acceleration ramp, which is
 * adequate here because the rig turns slowly.
 *
 * There are no endstops. Position is a step count relative to wherever the
 * axis was when the firmware started or was last zeroed.
 */

#ifndef STEPPER_H
#define STEPPER_H

#include <stdint.h>

typedef enum {
    AXIS_X = 0,
    AXIS_Y = 1,
    AXIS_COUNT = 2
} axis_t;

typedef enum {
    MOVE_OK = 0,
    MOVE_ERR_BUSY,
    MOVE_ERR_STEPS,
    MOVE_ERR_RATE
} move_result_t;

void stepper_init(void);

/*
 * Start a move. steps is signed and its sign sets the direction; rate is in
 * steps per second and is rejected outside STEP_RATE_MIN..STEP_RATE_MAX.
 * Returns MOVE_OK if the move started.
 */
move_result_t stepper_move(axis_t a, int32_t steps, uint16_t rate);

/* Stop both axes immediately, wherever they are. */
void stepper_abort(void);

uint8_t stepper_busy(axis_t a);

int32_t stepper_position(axis_t a);
void stepper_zero(axis_t a);

/* Whether the driver stays energised once a move finishes. */
void stepper_set_hold(axis_t a, uint8_t on);
uint8_t stepper_get_hold(axis_t a);

#endif /* STEPPER_H */
