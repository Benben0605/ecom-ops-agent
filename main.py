import readline
from src.agent import ChatSession

def main():
    print("私域电商运营 Agent（输入 q 退出）")
    chat_session = ChatSession(system_prompt="你是私域电商运营客服助手，负责订单查询、售后/政策咨询、商品推荐和运营数据分析，善于利用工具解决问题。必填参数齐全时直接调用工具，不要因为选填参数缺失而反问。")
    while True:
        user_input = input("你> ").strip()
        if user_input in {"q", "quit", "exit"}:
            break
        if not user_input:
            continue
        print("Agent>", chat_session.chat(user_input))


if __name__ == "__main__":
    main()
