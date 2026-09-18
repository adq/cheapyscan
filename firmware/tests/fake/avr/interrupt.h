/* SPDX-License-Identifier: MIT */
/* Copyright (c) 2026 Andrew de Quincey */

/*
 * Stand-in for <avr/interrupt.h> so the command parser in src/main.c can be
 * compiled and exercised on the host. Only the symbols main.c actually uses
 * are provided.
 */

#ifndef FAKE_AVR_INTERRUPT_H
#define FAKE_AVR_INTERRUPT_H

#define sei() ((void)0)
#define cli() ((void)0)

#endif /* FAKE_AVR_INTERRUPT_H */
