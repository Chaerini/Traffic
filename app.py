from gpiozero import PWMLED, DistanceSensor, MotionSensor
from signal import pause
from time import sleep
from flask import Flask, render_template, Response, jsonify, request
import requests
import spidev, cv2
import threading

app = Flask(__name__)

# 도로 신호등 (파랑, 빨강, 주황, 초록)
leds = [PWMLED(14), PWMLED(15), PWMLED(23), PWMLED(24)]

# 횡단보도 신호등 (빨강, 초록)
crosswalk_leds = [PWMLED(5), PWMLED(6)]

# 신호등 상태(도로 좌회전, 도로 직진, 횡단보도)
traffic_state = ["off", "off", "off"]

# 초음파 센서
distanceSensor = DistanceSensor(echo=20, trigger=21)

# 적외선 센서
motionSensor = MotionSensor(17)

# 조도 센서
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 100000

# 카메라 연결
def opencv():
    camera = cv2.VideoCapture(0, cv2.CAP_V4L2)
    if not camera.isOpened():
        print("카메라를 열 수 없습니다.")
        return
    
    camera.set(3, 320)
    camera.set(4, 240)

    while True:
        _, frame = camera.read()

        cv2.imshow("Frame", frame)

        if cv2.waitKey(1) == ord('q'):
            break
    
    camera.release()
    cv2.destroyAllWindow()

# 카메라 및 초음파 센서를 통한 차량 감지 함수
def detect_vehicle():
    for i in range(3):
        print("LED 상태:", traffic_state[i])  # 디버깅용 출력
    if distanceSensor.distance < 1.0: # 차량이 감지되었다면
        print(f"차량이 감지되었습니다 ! 거리: {distanceSensor.distance}")
        if traffic_state[2] == "off": # 횡단보도 신호가 꺼져있을 경우에만 좌회전 신호 ON
            traffic_state[0] = "on"
            traffic_control()
            sleep(5)
            traffic_state[0] = "off"
            traffic_control()
        else:
            print("횡단보도 신호등이 켜져있으므로 넘어갑니다.")
            pass
    else:
        pass

# 카메라 및 적외선 센서를 통한 사람 감지 함수
num = 1
def detect_person():
    global num
    if motionSensor.motion_detected and num % 150 == 0:  # 움직임 감지
        print("횡단보도에 사람이 감지되었습니다!")
        num += 1
        print("num :" + str(num))
        if traffic_state[2] == "off": # 횡단보도 신호가 꺼져있을 경우
            traffic_state[2] = "on"
            traffic_control()
            sleep(5)
            traffic_state[2] = "off"
            traffic_control()
            sleep(5)
            
        else:
            sleep(5)
            pass

    else:  # 움직임 없음
        print("횡단보도에 사람이 없습니다.")
        num += 1
        if traffic_state[1] == "off":
            pass


# 조도 센서 주어진 채널에서 ADC 값을 읽는 함수
def read_adc(channel): 
    adc = spi.xfer2([1, (8 + channel) << 4, 0])  # ADC에 요청 전송
    data = ((adc[1] & 3) << 8) + adc[2] # 결과 데이터 계산
    return data # ADC 값 반환

# 조도 센서를 통한 LED 밝기 조절 함수
# 조도 센서는 밝을수록 값이 커짐.
def led_brightness():
    print(f"밝기: {read_adc(0)}")
    if read_adc(0) < 500: # 어둡다면
        for led in leds:
            if led.is_lit:
                led.value = 1 # 모든 신호등을 최대 밝기로
        for cled in crosswalk_leds:
            if cled.is_lit:
                cled.value = 1
    else:
        for led in leds:
            if led.is_lit:
                led.value = 0.25 # 모든 신호등을 최소 밝기로
        for cled in crosswalk_leds:
            if cled.is_lit:
                cled.value = 0.25

# 신호등 상태에 따른 LED 조절
def traffic_control():
    # 좌회전 신호
    if traffic_state[0] == "on":
        print("좌회전 신호를 킵니다.")
        leds[0].on()
    else:
        print("좌회전 신호를 끕니다.")
        leds[0].off()

    # 직진 신호
    if traffic_state[0] == "off" and traffic_state[1] == "off" and traffic_state[2] == "off":
        print("아무 신호가 없으므로 직진 신호를 킵니다.")
        if crosswalk_leds[1].is_lit:
            crosswalk_leds[1].off()
            crosswalk_leds[0].on()
        leds[1].off()
        leds[2].on()
        sleep(3)
        leds[2].off()
        leds[3].on()
        traffic_state[1] = "on"

    elif traffic_state[1] == "on":
        if not leds[2].is_lit and not leds[3].is_lit:
            print("직진 신호를 킵니다.")
            leds[1].off()
            leds[2].on()
            sleep(3)
            leds[2].off()
            leds[3].on()
    else:
        print("직진 신호를 끕니다.")
        leds[3].off()
        leds[2].off()
        leds[1].on()

    # 횡단보도 신호
    if traffic_state[2] == "on":
        print("횡단보도 신호를 킵니다.")
        traffic_state[0] = "off"  # 횡단보도 신호가 켜지면 좌회전 신호 꺼짐

        if leds[3].is_lit:
            traffic_state[1] = "off"  # 횡단보도 신호가 켜지면 직진 신호 꺼짐
            leds[0].off()  # 좌회전 신호 끔

            if not leds[2].is_lit:
                leds[3].off()
                leds[2].on()
                sleep(5)
                leds[2].off()
                leds[1].on()
        
        crosswalk_leds[0].off()
        crosswalk_leds[1].on()
    else:
        print("횡단보도 신호를 끕니다.")
        crosswalk_leds[1].off()
        crosswalk_leds[0].on()

# 자동 감지 신호등
def run_traffic_system():
    while True:
        detect_vehicle()
        detect_person()
        led_brightness()
        sleep(0.5)

# 원격 신호등

def gen():
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    while True:
        ret, frame = camera.read()
        if not ret:
            continue
        
        retImg = frame
        
        # 프레임 저장
        cv2.imwrite("pic.jpg", retImg)

        yield (b"--frame\r\n"
        b"Content-Type: image/jpeg\r\n\r\n" + open("pic.jpg", "rb").read() + b"\r\n")
        
    camera.release()
    cv2.destroyAllWindows()

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/video_feed")
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/led_status")
def led_status_def():
    # 각 LED의 상태를 읽어와서 리스트로 만듭니다.
    led_status = [int(led.value > 0) for led in leds]  # 1이면 켜짐, 0이면 꺼짐
    return jsonify(led_status)

@app.route("/cross_status")
def cross_status_def():
    # 각 LED의 상태를 읽어와서 리스트로 만듭니다.
    cross_status = [int(led.value > 0) for led in crosswalk_leds]  # 1이면 켜짐, 0이면 꺼짐
    return jsonify(cross_status)

@app.route("/control_signal", methods=["POST"])
def control_signal():
    data = request.get_json()
    signal_type = data.get('type')
    action = data.get('action')
    
    if signal_type == "road":
        if action == "on":
            traffic_state[1] = "on"  # 도로 직진 신호 ON
        elif action == "off":
            traffic_state[1] = "off"  # 도로 직진 신호 OFF
    elif signal_type == "left":
        if action == "on":
            traffic_state[0] = "on"  # 좌회전 신호 ON
        elif action == "off":
            traffic_state[0] = "off"  # 좌회전 신호 OFF
    elif signal_type == "crosswalk":
        if action == "on":
            traffic_state[2] = "on"  # 횡단보도 신호 ON
        elif action == "off":
            traffic_state[2] = "off"  # 횡단보도 신호 OFF

    return {"traffic_state": traffic_state}

@app.route("/brightness")
def brightness():
    brightness_value = read_adc(0)  # 조도 센서에서 값을 읽음
    return jsonify({"brightness": brightness_value})
    
        
if __name__ == "__main__":
    # 트래픽 시스템을 별도의 스레드에서 실행
    traffic_thread = threading.Thread(target=run_traffic_system)
    traffic_thread.daemon = True  # 메인 프로그램 종료 시 스레드도 종료
    traffic_thread.start()
    
    app.run(host="0.0.0.0", port=5000)