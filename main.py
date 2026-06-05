from src import agent


def main():
    print("私域电商运营 Agent（输入 q 退出）")
    while True:
        user_input = input("你> ").strip()
        if user_input in {"q", "quit", "exit"}:
            break
        if not user_input:
            continue
        print("Agent>", agent.run(user_input))


if __name__ == "__main__":
    main()
