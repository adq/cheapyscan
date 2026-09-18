/*
 * config.h - hardware configuration for RAMPS 1.4 on an Arduino Mega 2560.
 *
 * Pin numbers below are the RAMPS 1.4 assignments as defined by Marlin in
 * Marlin/src/pins/ramps/pins_RAMPS.h, cross-checked against the RepRap wiki.
 * The AVR port and bit for each was taken from the Arduino core variant file
 * ArduinoCore-avr/variants/mega/pins_arduino.h.
 *
 *   signal        Arduino pin      AVR
 *   X step        54 (A0)          PORTF bit 0
 *   X direction   55 (A1)          PORTF bit 1
 *   X enable      38               PORTD bit 7
 *   Y step        60 (A6)          PORTF bit 6
 *   Y direction   61 (A7)          PORTF bit 7
 *   Y enable      56 (A2)          PORTF bit 2
 *
 * The A4988 ENABLE input is active low and has an internal pull-down, so the
 * drivers come up energised while the AVR pins are still high-impedance inputs
 * after reset. stepper_init() sets each PORT bit before its DDR bit so the
 * chosen state is applied without a glitch.
 */

#ifndef CONFIG_H
#define CONFIG_H

#ifndef F_CPU
#define F_CPU 16000000UL
#endif

#define BAUD_RATE 115200UL

/* X axis */
#define X_STEP_PORT PORTF
#define X_STEP_DDR  DDRF
#define X_STEP_BIT  PF0

#define X_DIR_PORT  PORTF
#define X_DIR_DDR   DDRF
#define X_DIR_BIT   PF1

#define X_EN_PORT   PORTD
#define X_EN_DDR    DDRD
#define X_EN_BIT    PD7

/* Y axis */
#define Y_STEP_PORT PORTF
#define Y_STEP_DDR  DDRF
#define Y_STEP_BIT  PF6

#define Y_DIR_PORT  PORTF
#define Y_DIR_DDR   DDRF
#define Y_DIR_BIT   PF7

#define Y_EN_PORT   PORTF
#define Y_EN_DDR    DDRF
#define Y_EN_BIT    PF2

/*
 * Set to 1 if a positive step count turns the axis the wrong way. This only
 * flips the logic level written to the direction pin, nothing else.
 */
#define X_DIR_INVERT 0
#define Y_DIR_INVERT 0

/*
 * Step pulse width in microseconds. The A4988 requires at least 1us high and
 * 1us low; 2us gives margin and still costs about 1 percent of interrupt time
 * at the maximum step rate.
 */
#define STEP_PULSE_US 2

/*
 * Step rate limits, in steps per second.
 *
 * Both timers run in CTC mode with a prescaler of 64, giving a 4us tick at
 * 16MHz. The compare value is (F_CPU / 64 / rate) - 1, so the rate range is
 * bounded at the low end by the 16-bit compare register and at the high end by
 * how much of the interrupt budget the step pulse is allowed to consume.
 *
 *   rate 10   -> compare 24999
 *   rate 4000 -> compare 61
 */
#define STEP_RATE_MIN     10u
#define STEP_RATE_MAX     4000u
#define STEP_RATE_DEFAULT 400u

#define TIMER_PRESCALER 64UL

/* Largest move accepted in a single command, in steps. */
#define STEP_COUNT_MAX 1000000L

/*
 * Whether each driver stays energised after a move completes.
 *
 * Default is on. An object mounted off the centre of the rotational axis will
 * sag under gravity the moment its driver releases, which loses the position
 * the firmware thinks it is at. Use the H command to release an axis when you
 * want it silent, for example during a long exposure.
 */
#define HOLD_DEFAULT 1

#endif /* CONFIG_H */
