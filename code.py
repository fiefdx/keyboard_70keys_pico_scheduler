import os
import gc
import time
import analogio
import board
import digitalio
import pwmio
import usb_hid
machine = None
microcontroller = None
try:
    import machine
except:
    try:
        import microcontroller
    except:
        print("no machine & microcontroller module support")
thread = None
try:
    import _thread as thread
except:
    print("no multi-threading module support")

from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.keycode import Keycode as K
from adafruit_hid.mouse import Mouse
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode as C

from scheduler import Scheluder, Condition, Task, Message
from common import ticks_ms, ticks_add, ticks_diff, sleep_ms

cpu_freq = 100000000
if machine:
    machine.freq(cpu_freq)
    print("freq: %s mhz" % (machine.freq() / 1000000))
if microcontroller:
    microcontroller.cpu.frequency = cpu_freq
    print("freq: %s mhz" % (microcontroller.cpu.frequency / 1000000))


FN = "FN"


def setup_pin(pin, direction, pull = None):
    io = digitalio.DigitalInOut(pin)
    io.direction = direction
    if pull is not None:
        io.pull = pull
    return io


def get_level_value(pin, max_level = 4096, zero_zone = 200, negative = 1):
    level_value = (pin.value * max_level) // 65536
    middle_value = max_level // 2
    value = middle_value - level_value
    if abs(value) < zero_zone:
        return 0
    elif abs(value) < (middle_value - (2 * zero_zone)):
        return value * negative
    else:
        return (value * middle_value * negative) // abs(value)


class Button(object):
    def __init__(self, pin, direction, pull):
        self.io = digitalio.DigitalInOut(pin)
        self.io.direction = direction
        self.io.pull = pull
        self.status = "up"

    def click(self):
        if self.status == "up":
            if self.down():
                self.status = "debounce"
        elif self.status == "debounce":
            if self.up():
                self.status = "up"
                return True
        return False

    def press(self):
        return self.status == "debounce"

    def continue_click(self):
        if self.status == "up":
            if self.down():
                self.status = "debounce"
                return True
        elif self.status == "debounce":
            if self.down():
                return True
            elif self.up():
                self.status = "up"
                return False
        return False

    def down(self):
        return not self.io.value

    def up(self):
        return self.io.value


class CustomKeyBoard(object):
    def __init__(self):
        time.sleep(1)
        self.keyboard = Keyboard(usb_hid.devices)
        self.keyboard_layout = KeyboardLayoutUS(self.keyboard)
        self.consumer_control = ConsumerControl(usb_hid.devices)
        self.x_lines = [
            setup_pin(board.GP4, digitalio.Direction.OUTPUT), # 0
            setup_pin(board.GP5, digitalio.Direction.OUTPUT), # 1
            setup_pin(board.GP6, digitalio.Direction.OUTPUT), # 2
            setup_pin(board.GP7, digitalio.Direction.OUTPUT), # 3
            setup_pin(board.GP8, digitalio.Direction.OUTPUT), # 4
            setup_pin(board.GP9, digitalio.Direction.OUTPUT), # 5
            setup_pin(board.GP10, digitalio.Direction.OUTPUT), # 6
            setup_pin(board.GP11, digitalio.Direction.OUTPUT), # 7
            setup_pin(board.GP12, digitalio.Direction.OUTPUT), # 8
            setup_pin(board.GP13, digitalio.Direction.OUTPUT), # 9
        ]
        self.y_lines = [
            setup_pin(board.GP14, digitalio.Direction.INPUT, digitalio.Pull.UP), # 0
            setup_pin(board.GP15, digitalio.Direction.INPUT, digitalio.Pull.UP), # 1
            setup_pin(board.GP16, digitalio.Direction.INPUT, digitalio.Pull.UP), # 2
            setup_pin(board.GP17, digitalio.Direction.INPUT, digitalio.Pull.UP), # 3
            setup_pin(board.GP18, digitalio.Direction.INPUT, digitalio.Pull.UP), # 4
            setup_pin(board.GP19, digitalio.Direction.INPUT, digitalio.Pull.UP), # 5
            setup_pin(board.GP20, digitalio.Direction.INPUT, digitalio.Pull.UP), # 6
        ]
        self.keys = [
            [K.Q, K.W, K.E, K.R, K.T, K.Y, K.U, K.I, K.O, K.P],
            [K.A, K.S, K.D, K.F, K.G, K.H, K.J, K.K, K.L, K.SEMICOLON],
            [K.Z, K.X, K.C, K.V, K.B, K.N, K.M, K.COMMA, K.PERIOD, K.FORWARD_SLASH],
            [K.ESCAPE, K.QUOTE, K.MINUS, K.EQUALS, K.SPACE, K.ENTER, K.LEFT_BRACKET, K.RIGHT_BRACKET, K.BACKSLASH, (K.BACKSPACE, K.PRINT_SCREEN)],
            [K.ONE, K.TWO, K.THREE, K.FOUR, K.FIVE, K.SIX, K.SEVEN, K.EIGHT, (K.NINE, K.PAGE_UP), (K.ZERO, K.PAGE_DOWN)],
            #[K.LEFT_SHIFT, (K.F1, K.F7), (K.F2, K.F8), (K.F3, K.F9), (K.F4, K.F10), (K.F5, K.F11), (K.F6, K.F12), (K.HOME, K.END), (K.CAPS_LOCK, K.DELETE), K.RIGHT_SHIFT],
            #[FN, K.WINDOWS ,K.TAB, K.LEFT_CONTROL, K.ALT, K.GRAVE_ACCENT, K.UP_ARROW, K.DOWN_ARROW, K.LEFT_ARROW, K.RIGHT_ARROW],
            [K.LEFT_SHIFT, K.TAB, K.LEFT_CONTROL, K.ALT, K.GRAVE_ACCENT, K.UP_ARROW, K.DOWN_ARROW, (K.LEFT_ARROW, K.PAGE_UP), (K.RIGHT_ARROW, K.PAGE_DOWN), K.RIGHT_SHIFT],
            [FN, K.WINDOWS , (K.F1, K.F7), (K.F2, K.F8), (K.F3, K.F9), (K.F4, K.F10), (K.F5, K.F11), (K.F6, K.F12), (K.HOME, K.END), (K.DELETE, K.CAPS_LOCK)],
        ]
        self.press_buttons = [
            [False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False],
            [False, False, False, False, False, False, False, False, False, False],
        ]
        self.buttons = []
        self.release = []

    def press_keys(self, keys = []):
        self.buttons = []
        self.keyboard.press(*keys)
        self.keyboard.release(*keys)
        self.release.clear()

    def scan(self):
        for x in range(10):
            for i in range(10):
                if i == x:
                    self.x_lines[i].value = False # scan x line
                else:
                    self.x_lines[i].value = True # disable other lines
            for y in range(6, -1, -1):
                if self.y_lines[y].value == False: # pressd
                    if self.press_buttons[y][x]: # y,x pressed, already pressed
                        pass
                    else: # y,x not pressed, first press
                        if self.press_buttons[6][0]: # fn pressed
                            if y == 6 and x == 0:
                                pass
                            else:
                                if isinstance(self.keys[y][x], tuple):
                                    self.buttons.append(self.keys[y][x][1])
                                else:
                                    self.buttons.append(self.keys[y][x])
                        else:
                            if y == 6 and x == 0:
                                pass
                            else:
                                if isinstance(self.keys[y][x], tuple):
                                    self.buttons.append(self.keys[y][x][0])
                                else:
                                    self.buttons.append(self.keys[y][x])
                        self.press_buttons[y][x] = True
                else: # not press
                    if self.press_buttons[y][x]:
                        self.press_buttons[y][x] = False
                        if y == 6 and x == 0:
                            pass
                        else:
                            if isinstance(self.keys[y][x], tuple):
                                if self.keys[y][x][0] in self.buttons:
                                    self.buttons.remove(self.keys[y][x][0])
                                    self.release.append(self.keys[y][x][0])
                                else:
                                    self.buttons.remove(self.keys[y][x][1])
                                    self.release.append(self.keys[y][x][1])
                            else:
                                if self.keys[y][x] in self.buttons:
                                    self.buttons.remove(self.keys[y][x])
                                self.release.append(self.keys[y][x])
        if self.press_buttons[6][0]:
            if K.UP_ARROW in self.buttons:
                self.consumer_control.send(C.VOLUME_INCREMENT)
                self.buttons.remove(K.UP_ARROW)
            elif K.DOWN_ARROW in self.buttons:
                self.consumer_control.send(C.VOLUME_DECREMENT)
                self.buttons.remove(K.DOWN_ARROW)
        try:
            self.keyboard.press(*self.buttons)
            self.keyboard.release(*self.release)
            self.release.clear() # = []
        except Exception as e:
            self.release.clear()
            try:
                self.keyboard.release_all()
            except Exception as e:
                print("release_all keys error: ", e)
            try:
                time.sleep(1)
                self.keyboard = Keyboard(usb_hid.devices)
            except Exception as e:
                print("reinit keyboard error: ", e)
            print(e)


def monitor(task, name, scheduler = None, display_id = None):
    while True:
        gc.collect()
        monitor_msg = "CPU%s:%3d%%  RAM:%3d%%" % (scheduler.cpu, int(100 - scheduler.idle), int(100 - (scheduler.mem_free() * 100 / (264 * 1024))))
        yield Condition(sleep = 2000, send_msgs = [Message({"msg": monitor_msg}, receiver = display_id)])


def display(task, name):
    while True:
        yield Condition(sleep = 0, wait_msg = True)
        msg = task.get_message()
        print(msg.content["msg"])


def keyboard_scan(task, name, interval = 50, display_id = None):
    k = CustomKeyBoard()
    while True:
        t = ticks_ms()
        try:
            k.scan()
        except Exception as e:
            print(e)
        tt = ticks_ms()
        sleep_time = interval - ticks_diff(tt, t)
        if sleep_time > 0:
            yield Condition(sleep = sleep_time)
        else:
            yield Condition(sleep = 0)


def mouse_scan(task, name, interval = 50, display_id = None):
    time.sleep(1)
    mouse = Mouse(usb_hid.devices)
    x_axis = analogio.AnalogIn(board.A1)
    y_axis = analogio.AnalogIn(board.A0)
    mouse_left_button = Button(board.GP0, digitalio.Direction.INPUT, digitalio.Pull.UP)
    mouse_right_button = Button(board.GP1, digitalio.Direction.INPUT, digitalio.Pull.UP)
    mouse_wheel_up_button = Button(board.GP2, digitalio.Direction.INPUT, digitalio.Pull.UP)
    mouse_wheel_down_button = Button(board.GP3, digitalio.Direction.INPUT, digitalio.Pull.UP)
    while True:
        t = ticks_ms()
        x = get_level_value(y_axis, negative = -1)
        y = get_level_value(x_axis, negative = -1)

        if mouse_left_button.click():
            mouse.click(Mouse.LEFT_BUTTON)
        if mouse_left_button.press():
            mouse.press(Mouse.LEFT_BUTTON)
        if mouse_right_button.click():
            mouse.click(Mouse.RIGHT_BUTTON)
        if mouse_right_button.press():
            mouse.press(Mouse.RIGHT_BUTTON)
        if mouse_wheel_up_button.continue_click(): # or mouse_wheel_up_button.press():
            mouse.move(wheel = 1)
        elif mouse_wheel_down_button.continue_click(): # or mouse_wheel_down_button.press():
            mouse.move(wheel = -1)
        mouse.move(x = x // 120, y = y // 120)
        tt = ticks_ms()
        sleep_time = interval - ticks_diff(tt, t)
        if sleep_time > 0:
            yield Condition(sleep = sleep_time)
        else:
            yield Condition(sleep = 0)


def brightness_control(task, name, interval = 50, display_id = None):
    light = 10
    light_min = 0
    light_max = 90
    light_pwm = pwmio.PWMOut(board.GP28, frequency = 2000)
    light_up_button = Button(board.GP22, digitalio.Direction.INPUT, digitalio.Pull.UP)
    light_down_button = Button(board.GP21, digitalio.Direction.INPUT, digitalio.Pull.UP)

    def set_light(percent):
        light_pwm.duty_cycle = int((100 - percent) * 65535 / 100)

    set_light(light)
    while True:
        t = ticks_ms()
        if light_up_button.click():
            light += 5
            if light > light_max:
                light = light_max
            print(light)
            set_light(light)
        elif light_down_button.click():
            light -= 5
            if light < light_min:
                light = light_min
            print(light)
            set_light(light)
        tt = ticks_ms()
        sleep_time = interval - ticks_diff(tt, t)
        if sleep_time > 0:
            yield Condition(sleep = sleep_time)
        else:
            yield Condition(sleep = 0)


def led_breath(task, name, interval = 500, display_id = None):
    led = setup_pin(board.GP25, digitalio.Direction.OUTPUT) # breathing light for status checking
    led.value = True
    yield Condition(sleep = interval)
    while True:
        led.value = not led.value
        yield Condition(sleep = interval)


if __name__ == "__main__":
    try:
        s = Scheluder(cpu = 0)
        display_id = s.add_task(Task(display, "display"))
        monitor_id = s.add_task(Task(monitor, "monitor", kwargs = {"scheduler": s, "display_id": display_id}))
        keyboard_id = s.add_task(Task(keyboard_scan, "keyboard", kwargs = {"interval": 50, "display_id": display_id}))
        mouse_id = s.add_task(Task(mouse_scan, "mouse", kwargs = {"interval": 25, "display_id": display_id}))
        brightness_id = s.add_task(Task(brightness_control, "brightness", kwargs = {"interval": 50, "display_id": display_id}))
        led_id = s.add_task(Task(led_breath, "led", kwargs = {"interval": 500, "display_id": display_id}))
        s.run()
    except Exception as e:
        print("main: %s" % str(e))
