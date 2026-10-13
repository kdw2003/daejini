from daejini.bot import reply

if __name__ == "__main__":
    print("대지니: 안녕하세요, 경제 비서 대지니예요. (종료: '종료')")
    while True:
        text = input("나: ").strip()
        if text in ("종료", "quit", "exit"):
            print("대지니: 다음에 또 봐요!")
            break
        if text:
            print("대지니:", reply(text))
