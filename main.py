import readline
from src.agent import ChatSession

def main():
    print("私域电商运营 Agent（输入 q 退出）")
    chat_session = ChatSession("你是私域电商运营客服助手，负责订单查询和售后/政策咨询，善于利用工具解决问题")
    while True:
        user_input = input("你> ").strip()
        if user_input in {"q", "quit", "exit"}:
            break
        if not user_input:
            continue
        print("Agent>", chat_session.chat(user_input))


if __name__ == "__main__":
    main()
