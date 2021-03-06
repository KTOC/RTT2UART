import logging
import pylink
import time
import serial
import threading

logging.basicConfig(level=logging.NOTSET,
                    format='%(asctime)s - [%(levelname)s] (%(filename)s:%(lineno)d) - %(message)s')
logger = logging.getLogger(__name__)


class rtt_to_serial():
    def __init__(self, device, port=None, baudrate=115200, interface=pylink.enums.JLinkInterfaces.SWD, speed=12000, reset=False):
        # 目标芯片名字
        self.device = device
        # 调试口
        self._interface = interface
        # 连接速率
        self._speed = speed
        # 复位标志
        self._reset = reset

        # segger rtt上下通道缓存大小
        self.upbuffer_size = 1024
        self.downbuffer_size = 512

        # 串口参数
        self.port = port
        self.baudrate = baudrate

        # 线程
        self.rtt2uart = None
        self.uart2rtt = None
        self.thread_switch = False

        try:
            self.jlink = pylink.JLink()
        except:
            logger.error('Find jlink dll failed', exc_info=True)
            raise

        try:
            self.serial = serial.Serial()
        except:
            logger.error('Creat serial object failed', exc_info=True)
            raise

    def __del__(self):
        self.jlink.close()
        self.serial.close()

    def start(self):
        try:
            if self.jlink.connected() == False:
                # 加载jlinkARM.dll
                self.jlink.open()

                # 设置连接速率
                if self.jlink.set_speed(self._speed) == False:
                    logger.error('Set speed failed', exc_info=True)
                    raise

                # 设置连接接口为SWD
                if self.jlink.set_tif(self._interface) == False:
                    logger.error('Set interface failed', exc_info=True)
                    raise

                try:
                    # 连接目标芯片
                    self.jlink.connect(self.device)
                    # 启动RTT，对于RTT的任何操作都需要在RTT启动后进行
                    self.jlink.rtt_start()

                    if self._reset == True:
                        # 复位一下目标芯片，复位后不要停止芯片，保证后续操作的稳定性
                        self.jlink.reset(halt=False)

                except pylink.errors.JLinkException:
                    logger.error('Connect target failed', exc_info=True)
                    raise

        except pylink.errors.JLinkException as errors:
            logger.error('Open jlink failed', exc_info=True)
            raise

        try:
            if self.serial.isOpen() == False:
                # 设置串口参数并打开串口
                self.serial.port = self.port
                self.serial.baudrate = self.baudrate
                self.serial.timeout = 0
                self.serial.write_timeout = 0
                self.serial.open()
        except:
            logger.error('Open serial failed', exc_info=True)
            raise

        self.thread_switch = True
        self.rtt2uart = threading.Thread(target=self.rtt_to_uart)
        self.uart2rtt = threading.Thread(target=self.uart_to_rtt)
        self.rtt2uart.start()
        self.uart2rtt.start()

    def stop(self):
        self.thread_switch = False
        # 等待线程结束
        if self.rtt2uart.is_alive():
            self.rtt2uart.join()

        if self.uart2rtt.is_alive():
            self.uart2rtt.join()

        try:
            if self.jlink.connected() == True:
                # 使用完后停止RTT
                self.jlink.rtt_stop()
                # 释放之前加载的jlinkARM.dll
                self.jlink.close()
        except pylink.errors.JLinkException:
            logger.error('Disconnect target failed', exc_info=True)
            pass

        try:
            if self.serial.isOpen() == True:
                self.serial.close()
        except:
            logger.error('Close serial failed', exc_info=True)
            pass

    def rtt_to_uart(self):
        while self.thread_switch == True:
            try:
                rtt_recv = self.jlink.rtt_read(0, self.upbuffer_size)
            except:
                raise Exception("Jlink rtt read error")

            if len(rtt_recv):
                try:
                    self.serial.write(bytes(rtt_recv))
                except:
                    raise Exception("Serial write error")

    def uart_to_rtt(self):
        while self.thread_switch == True:
            # 查看是否有串口数据
            num = self.serial.inWaiting()

            # 有数据则将数据读取出来
            if num:
                try:
                    data = self.serial.read(num)
                except:
                    raise Exception("Serial read error")

                # 将读出的数据写入到rtt
                write_index = 0
                while write_index < len(data):
                    try:
                        bytes_written = self.jlink.rtt_write(
                            0, list(data[write_index:]))
                    except:
                        raise Exception("Jlink rtt write error")

                    write_index = write_index + bytes_written


if __name__ == "__main__":
    serial_name = input("请输入虚拟串口对中的串口名字，如COM26：")

    if '' == serial_name:
        serial_name = 'COM26'

    test = rtt_to_serial('AMAPH1KK-KBR', serial_name, 115200)
    test.start()
