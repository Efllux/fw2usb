CC = clang
CFLAGS = -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter
FRAMEWORKS = -framework CoreAudio -framework CoreFoundation
BUILD = ../../target/coreaudio
.PHONY: all check clean
all: $(BUILD)/fw2usb.driver/Contents/MacOS/fw2usb
$(BUILD):
	mkdir -p $@
$(BUILD)/fw2usb.driver/Contents/MacOS/fw2usb: src/Driver.c Info.plist | $(BUILD)
	mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -bundle $< $(FRAMEWORKS) -o $@
	cp Info.plist $(BUILD)/fw2usb.driver/Contents/Info.plist
$(BUILD)/contract: src/Driver.c tests/contract.c | $(BUILD)
	$(CC) $(CFLAGS) $^ $(FRAMEWORKS) -o $@
check: all $(BUILD)/contract
	$(BUILD)/contract
clean:
	rm -rf $(BUILD)
