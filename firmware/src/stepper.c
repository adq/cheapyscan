/* SPDX-License-Identifier: MIT */
/* Copyright (c) 2026 Andrew de Quincey */

#include "config.h"
#include "stepper.h"

#include <avr/io.h>
#include <avr/interrupt.h>
#include <util/atomic.h>
#include <util/delay.h>

#define PIN_SET(port, bit) do { (port) |= (uint8_t)_BV(bit); } while (0)
#define PIN_CLR(port, bit) do { (port) &= (uint8_t)~_BV(bit); } while (0)

/*
 * Written by the timer interrupts, read by the main loop. The 32-bit values
 * are not read atomically on an 8-bit core, so the accessors below take a
 * critical section.
 */
static volatile int32_t  s_position[AXIS_COUNT];
static volatile uint32_t s_remaining[AXIS_COUNT];
static volatile int8_t   s_step_delta[AXIS_COUNT];
static volatile uint8_t  s_busy[AXIS_COUNT];

/* Read by the timer interrupts when a move finishes, so it must be volatile. */
static volatile uint8_t s_hold[AXIS_COUNT];

/* ---------------------------------------------------------------- pins --- */

/*
 * These take a compile-time constant axis at every call site, so the branch
 * folds away and each one becomes a single instruction.
 */

static inline void step_pulse(axis_t a)
{
    if (a == AXIS_X) {
        PIN_SET(X_STEP_PORT, X_STEP_BIT);
    } else {
        PIN_SET(Y_STEP_PORT, Y_STEP_BIT);
    }

    _delay_us(STEP_PULSE_US);

    if (a == AXIS_X) {
        PIN_CLR(X_STEP_PORT, X_STEP_BIT);
    } else {
        PIN_CLR(Y_STEP_PORT, Y_STEP_BIT);
    }
}

static void set_direction(axis_t a, uint8_t forward)
{
    uint8_t level;

    if (a == AXIS_X) {
        level = X_DIR_INVERT ? !forward : forward;
        if (level) {
            PIN_SET(X_DIR_PORT, X_DIR_BIT);
        } else {
            PIN_CLR(X_DIR_PORT, X_DIR_BIT);
        }
    } else {
        level = Y_DIR_INVERT ? !forward : forward;
        if (level) {
            PIN_SET(Y_DIR_PORT, Y_DIR_BIT);
        } else {
            PIN_CLR(Y_DIR_PORT, Y_DIR_BIT);
        }
    }
}

/* The A4988 ENABLE input is active low. */
static void set_driver(axis_t a, uint8_t energised)
{
    if (a == AXIS_X) {
        if (energised) {
            PIN_CLR(X_EN_PORT, X_EN_BIT);
        } else {
            PIN_SET(X_EN_PORT, X_EN_BIT);
        }
    } else {
        if (energised) {
            PIN_CLR(Y_EN_PORT, Y_EN_BIT);
        } else {
            PIN_SET(Y_EN_PORT, Y_EN_BIT);
        }
    }
}

/* -------------------------------------------------------------- timers --- */

static void timer_start(axis_t a, uint16_t compare)
{
    if (a == AXIS_X) {
        TCNT1 = 0;
        OCR1A = compare;
        TIFR1 = (uint8_t)_BV(OCF1A);            /* discard any stale match */
        TIMSK1 |= (uint8_t)_BV(OCIE1A);
        TCCR1B = (uint8_t)(_BV(WGM12) | _BV(CS11) | _BV(CS10));  /* CTC, /64 */
    } else {
        TCNT3 = 0;
        OCR3A = compare;
        TIFR3 = (uint8_t)_BV(OCF3A);
        TIMSK3 |= (uint8_t)_BV(OCIE3A);
        TCCR3B = (uint8_t)(_BV(WGM32) | _BV(CS31) | _BV(CS30));
    }
}

static void timer_stop(axis_t a)
{
    if (a == AXIS_X) {
        TCCR1B = 0;
        TIMSK1 &= (uint8_t)~_BV(OCIE1A);
    } else {
        TCCR3B = 0;
        TIMSK3 &= (uint8_t)~_BV(OCIE3A);
    }
}

/* ---------------------------------------------------------------- core --- */

static inline void axis_finish(axis_t a)
{
    timer_stop(a);
    s_remaining[a] = 0;
    s_busy[a] = 0;

    if (!s_hold[a]) {
        set_driver(a, 0);
    }
}

static inline void axis_tick(axis_t a)
{
    if (s_remaining[a] == 0UL) {
        axis_finish(a);
        return;
    }

    step_pulse(a);
    s_position[a] += s_step_delta[a];

    if (--s_remaining[a] == 0UL) {
        axis_finish(a);
    }
}

ISR(TIMER1_COMPA_vect)
{
    axis_tick(AXIS_X);
}

ISR(TIMER3_COMPA_vect)
{
    axis_tick(AXIS_Y);
}

/* ----------------------------------------------------------------- api --- */

void stepper_init(void)
{
    uint8_t i;

    /*
     * Belt and braces, not a requirement. On the ATmega2560 the JTAG interface
     * sits on PF4 to PF7, which covers Y step (PF6) and Y direction (PF7).
     *
     * A stock Mega 2560 has a high fuse of 0xD8, leaving JTAGEN unprogrammed,
     * so those are already ordinary port pins. Neither Marlin nor grbl-Mega
     * bothers to disable JTAG, and both drive these same pins successfully.
     *
     * This only matters on a board whose fuses were changed to enable JTAG
     * (high fuse 0x18), where the Y axis would silently never move. Writing JTD
     * twice within four clock cycles costs 18 bytes and removes that failure
     * mode, so the firmware does not depend on the fuse being right.
     */
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        MCUCR |= (uint8_t)_BV(JTD);
        MCUCR |= (uint8_t)_BV(JTD);
    }

    for (i = 0; i < (uint8_t)AXIS_COUNT; i++) {
        s_position[i] = 0;
        s_remaining[i] = 0;
        s_step_delta[i] = 1;
        s_busy[i] = 0;
        s_hold[i] = HOLD_DEFAULT;
    }

    /*
     * Set each output level before switching the pin to an output, so the
     * chosen state is applied without a transient. This matters for the enable
     * pins: the A4988 has an internal pull-down on ENABLE, so the drivers are
     * already energised while these pins are still inputs after reset.
     */
    set_driver(AXIS_X, HOLD_DEFAULT);
    set_driver(AXIS_Y, HOLD_DEFAULT);

    PIN_CLR(X_STEP_PORT, X_STEP_BIT);
    PIN_CLR(Y_STEP_PORT, Y_STEP_BIT);
    set_direction(AXIS_X, 1);
    set_direction(AXIS_Y, 1);

    PIN_SET(X_STEP_DDR, X_STEP_BIT);
    PIN_SET(X_DIR_DDR,  X_DIR_BIT);
    PIN_SET(X_EN_DDR,   X_EN_BIT);
    PIN_SET(Y_STEP_DDR, Y_STEP_BIT);
    PIN_SET(Y_DIR_DDR,  Y_DIR_BIT);
    PIN_SET(Y_EN_DDR,   Y_EN_BIT);

    /* Normal port operation on the compare outputs; CTC is selected in TCCRnB. */
    TCCR1A = 0;
    TCCR1B = 0;
    TCCR3A = 0;
    TCCR3B = 0;
}

move_result_t stepper_move(axis_t a, int32_t steps, uint16_t rate)
{
    uint32_t count;
    uint16_t compare;

    if (stepper_busy(a)) {
        return MOVE_ERR_BUSY;
    }
    if (steps == 0 || steps > STEP_COUNT_MAX || steps < -STEP_COUNT_MAX) {
        return MOVE_ERR_STEPS;
    }
    if (rate < STEP_RATE_MIN || rate > STEP_RATE_MAX) {
        return MOVE_ERR_RATE;
    }

    if (steps < 0) {
        count = (uint32_t)(-steps);
        set_direction(a, 0);
    } else {
        count = (uint32_t)steps;
        set_direction(a, 1);
    }

    compare = (uint16_t)((F_CPU / TIMER_PRESCALER / (uint32_t)rate) - 1UL);

    /*
     * The direction pin is set above and the first step cannot occur until the
     * timer has counted out a full period, which is at least 250us even at the
     * maximum rate. That is far beyond the 200ns direction setup the A4988
     * requires.
     */
    set_driver(a, 1);

    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        s_step_delta[a] = (steps < 0) ? -1 : 1;
        s_remaining[a] = count;
        s_busy[a] = 1;
        timer_start(a, compare);
    }

    return MOVE_OK;
}

void stepper_abort(void)
{
    uint8_t i;

    for (i = 0; i < (uint8_t)AXIS_COUNT; i++) {
        ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
            timer_stop((axis_t)i);
            s_remaining[i] = 0;
            s_busy[i] = 0;
        }
        if (!s_hold[i]) {
            set_driver((axis_t)i, 0);
        }
    }
}

uint8_t stepper_busy(axis_t a)
{
    return s_busy[a];  /* single byte, so the read is already atomic */
}

int32_t stepper_position(axis_t a)
{
    int32_t v;

    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        v = s_position[a];
    }
    return v;
}

void stepper_zero(axis_t a)
{
    ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
        s_position[a] = 0;
    }
}

void stepper_set_hold(axis_t a, uint8_t on)
{
    s_hold[a] = on ? 1 : 0;

    if (on) {
        set_driver(a, 1);
    } else if (!stepper_busy(a)) {
        set_driver(a, 0);
    }
    /* If the axis is moving, the release happens when the move finishes. */
}

uint8_t stepper_get_hold(axis_t a)
{
    return s_hold[a];
}
