# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Andrew de Quincey

# Firmware for an Arduino Mega 2560 with a RAMPS 1.4 shield.
#
#   make          build build/cheapscan.hex
#   make size     report flash and RAM usage
#   make flash    upload over USB
#   make clean
#
# Override the serial port if it is not the default:
#   make flash PORT=/dev/ttyACM1

MCU       = atmega2560
F_CPU     = 16000000UL
PORT     ?= /dev/ttyACM0
PROGRAMMER = wiring
UPLOAD_BAUD = 115200

TARGET = cheapscan
BUILD  = build
SRC    = src/main.c src/uart.c src/stepper.c
OBJ    = $(SRC:src/%.c=$(BUILD)/%.o)
DEP    = $(OBJ:.o=.d)

CC      = avr-gcc
OBJCOPY = avr-objcopy
SIZE    = avr-size
AVRDUDE = avrdude

CFLAGS = -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Os -std=gnu11 \
         -Wall -Wextra -Wundef -Wshadow -Wconversion \
         -Werror=implicit-function-declaration \
         -ffunction-sections -fdata-sections -flto \
         -Isrc -MMD -MP

LDFLAGS = -mmcu=$(MCU) -Wl,--gc-sections -flto

.PHONY: all size flash clean

all: $(BUILD)/$(TARGET).hex

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/%.o: src/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/$(TARGET).elf: $(OBJ)
	$(CC) $(LDFLAGS) $^ -o $@

$(BUILD)/$(TARGET).hex: $(BUILD)/$(TARGET).elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@
	@$(SIZE) --format=avr --mcu=$(MCU) $<

size: $(BUILD)/$(TARGET).elf
	$(SIZE) --format=avr --mcu=$(MCU) $<

flash: $(BUILD)/$(TARGET).hex
	$(AVRDUDE) -p m2560 -c $(PROGRAMMER) -P $(PORT) -b $(UPLOAD_BAUD) \
	           -D -U flash:w:$<:i

clean:
	rm -rf $(BUILD)

-include $(DEP)
