# -*- coding: utf-8 -*-
"""
测试用例自动生成器

功能说明：
1. 从 Chroma 向量库中检索最相关的测试规范上下文
2. 使用结构化 Prompt + Few-Shot 提示词引导 LLM
3. 调用 OpenAI/DeepSeek API 生成标准 JSON 格式的测试用例
4. 输出包含：用例编号、测试点、前置条件、操作步骤、预期结果

环境变量配置：
- OPENAI_API_KEY: OpenAI API 密钥
- OPENAI_BASE_URL: API 基础 URL（可选，用于兼容 DeepSeek 等）
- MODEL_NAME: 模型名称（默认：gpt-3.5-turbo）

依赖安装：
pip install openai langchain langchain-community chromadb
"""

import os
import json

from . import config
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from openai import OpenAI


def load_vectorstore(persist_directory="./chroma_db"):
    """
    加载已保存的 Chroma 向量数据库
    
    参数:
        persist_directory: 向量数据库持久化目录
    
    返回:
        vectorstore: Chroma 向量数据库实例
    """
    print("正在加载向量数据库...")
    
    # 创建 Embedding 模型（与构建时使用的模型保持一致）
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-base-zh-v1.5",
        model_kwargs={'device': 'cpu'},
        encode_kwargs={'normalize_embeddings': True},
    )
    
    # 加载已保存的向量数据库
    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings
    )
    
    print(f"  ✓ 向量数据库加载成功: {persist_directory}")
    return vectorstore


def retrieve_context(vectorstore, query, top_k=3):
    """
    从向量库中检索最相关的测试规范上下文
    
    参数:
        vectorstore: Chroma 向量数据库实例
        query: 用户输入的查询文本
        top_k: 返回最相关的 Top-K 条结果
    
    返回:
        context_text: 拼接后的上下文文本
        results: 原始检索结果列表
    """
    print(f"\n正在检索相关规范上下文...")
    print(f"  查询: {query}")
    print(f"  检索数量: Top-{top_k}")
    
    # 执行相似度检索
    results = vectorstore.similarity_search(query, k=top_k)
    
    # 拼接检索结果为上下文文本
    context_parts = []
    for i, result in enumerate(results, 1):
        source_file = result.metadata.get('source_file', '未知')
        content = result.page_content
        context_parts.append(f"[规范片段 {i}] (来源: {source_file})\n{content}")
    
    context_text = "\n\n".join(context_parts)
    
    print(f"  ✓ 检索到 {len(results)} 条相关规范")
    return context_text, results


def build_system_prompt(context, user_requirement):
    """
    构建结构化的 System Prompt，包含 Few-Shot 示例
    
    参数:
        context: 从向量库检索到的测试规范上下文
        user_requirement: 用户的测试需求描述
    
    返回:
        system_prompt: 完整的系统提示词
        user_prompt: 用户提示词
    """
    
    # System Prompt：定义角色、任务、约束和 Few-Shot 示例
    system_prompt = f"""你是一个资深测试开发专家，拥有 10 年以上的软件测试经验。

你的任务是根据用户提供的测试需求，结合相关的测试规范，设计高质量的标准测试用例。

## 测试用例要求：
1. 运用等价类划分法和边界值分析法设计测试用例
2. 覆盖正常流程和异常流程
3. 测试用例应该具有可执行性和可验证性
4. 预期结果应该明确且可验证

## 输出格式约束：
你必须且只能输出合法的 JSON 格式，不要包含任何其他文字说明。
JSON 格式如下：
{{
  "test_cases": [
    {{
      "case_id": "TC001",
      "test_point": "测试点描述",
      "precondition": "前置条件",
      "steps": ["步骤1", "步骤2", "步骤3"],
      "expected_result": "预期结果",
      "priority": "P0/P1/P2",
      "test_type": "功能测试/边界测试/异常测试"
    }}
  ]
}}

## 参考的测试规范上下文：
{context}
"""
    
    # Few-Shot 示例：提供 2 个完整的测试用例示例
    few_shot_examples = """
## 示例 1：
用户输入：用户登录功能，包含用户名和密码

输出：
{{
  "test_cases": [
    {{
      "case_id": "TC001",
      "test_point": "正常登录 - 正确的用户名和密码",
      "precondition": "用户已注册，账号存在且状态正常",
      "steps": [
        "打开登录页面",
        "输入正确的用户名",
        "输入正确的密码",
        "点击登录按钮"
      ],
      "expected_result": "登录成功，跳转到用户首页，显示欢迎信息",
      "priority": "P0",
      "test_type": "功能测试"
    }},
    {{
      "case_id": "TC002",
      "test_point": "边界值 - 用户名长度为最小值（1个字符）",
      "precondition": "系统中存在用户名为单个字符的用户",
      "steps": [
        "打开登录页面",
        "输入1个字符的用户名",
        "输入正确的密码",
        "点击登录按钮"
      ],
      "expected_result": "登录成功，系统正常处理最短用户名",
      "priority": "P1",
      "test_type": "边界测试"
    }},
    {{
      "case_id": "TC003",
      "test_point": "异常测试 - 密码错误",
      "precondition": "用户已注册，账号存在",
      "steps": [
        "打开登录页面",
        "输入正确的用户名",
        "输入错误的密码",
        "点击登录按钮"
      ],
      "expected_result": "登录失败，显示'用户名或密码错误'提示，不跳转到首页",
      "priority": "P0",
      "test_type": "异常测试"
    }},
    {{
      "case_id": "TC004",
      "test_point": "边界值 - 密码长度超过最大值",
      "precondition": "无",
      "steps": [
        "打开登录页面",
        "输入正确的用户名",
        "输入超过最大长度限制的密码（如129个字符）",
        "点击登录按钮"
      ],
      "expected_result": "系统应拒绝超长密码，显示'密码长度不能超过128个字符'提示",
      "priority": "P1",
      "test_type": "边界测试"
    }},
    {{
      "case_id": "TC005",
      "test_point": "异常测试 - 用户名为空",
      "precondition": "无",
      "steps": [
        "打开登录页面",
        "不输入用户名",
        "输入密码",
        "点击登录按钮"
      ],
      "expected_result": "登录失败，显示'用户名不能为空'提示，登录按钮可继续点击",
      "priority": "P1",
      "test_type": "异常测试"
    }}
  ]
}}

## 示例 2：
用户输入：文件上传功能，支持 JPG 和 PNG 格式，最大 5MB

输出：
{{
  "test_cases": [
    {{
      "case_id": "TC001",
      "test_point": "正常上传 - 符合要求的JPG图片",
      "precondition": "用户已登录系统，进入文件上传页面",
      "steps": [
        "点击上传按钮",
        "选择一个2MB的JPG格式图片",
        "确认上传"
      ],
      "expected_result": "上传成功，显示上传进度条，完成后显示预览图",
      "priority": "P0",
      "test_type": "功能测试"
    }},
    {{
      "case_id": "TC002",
      "test_point": "边界值 - 文件大小恰好为5MB",
      "precondition": "用户已登录系统",
      "steps": [
        "点击上传按钮",
        "选择一个恰好5MB的PNG图片",
        "确认上传"
      ],
      "expected_result": "上传成功，5MB是允许的最大值，系统正常处理",
      "priority": "P1",
      "test_type": "边界测试"
    }},
    {{
      "case_id": "TC003",
      "test_point": "边界值 - 文件大小超过5MB（5.1MB）",
      "precondition": "用户已登录系统",
      "steps": [
        "点击上传按钮",
        "选择一个5.1MB的JPG图片",
        "确认上传"
      ],
      "expected_result": "上传失败，显示'文件大小不能超过5MB'提示",
      "priority": "P0",
      "test_type": "边界测试"
    }},
    {{
      "case_id": "TC004",
      "test_point": "异常测试 - 上传不支持的文件格式（PDF）",
      "precondition": "用户已登录系统",
      "steps": [
        "点击上传按钮",
        "选择一个PDF文件",
        "确认上传"
      ],
      "expected_result": "上传失败，显示'仅支持JPG和PNG格式'提示",
      "priority": "P0",
      "test_type": "异常测试"
    }},
    {{
      "case_id": "TC005",
      "test_point": "异常测试 - 上传空文件（0字节）",
      "precondition": "用户已登录系统",
      "steps": [
        "点击上传按钮",
        "选择一个0字节的JPG文件",
        "确认上传"
      ],
      "expected_result": "上传失败，显示'文件不能为空'提示",
      "priority": "P1",
      "test_type": "异常测试"
    }}
  ]
}}
"""
    
    # User Prompt：用户的具体需求
    user_prompt = f"""{few_shot_examples}

现在请为以下需求设计测试用例：

用户需求：{user_requirement}

请严格按照上述 JSON 格式输出测试用例，至少包含 5 个测试用例，覆盖正常流程、边界值和异常情况。
只输出 JSON，不要包含任何其他说明文字。"""
    
    return system_prompt, user_prompt


def call_llm_api(system_prompt, user_prompt, temperature=0.7, max_tokens=4000, response_format=None):
    """
    调用 OpenAI/DeepSeek API 生成测试用例
    
    参数:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
    
    返回:
        response_text: LLM 返回的文本
    """
    print("\n正在调用 LLM 生成测试用例...")

    # 统一从 config 读取配置（自动加载 .env，不打印密钥）
    llm_cfg = config.get_llm_config()
    api_key = llm_cfg["api_key"]
    base_url = llm_cfg["base_url"]
    model_name = llm_cfg["model"]

    if not api_key:
        raise ValueError("未设置 OPENAI_API_KEY 环境变量")

    print(f"  API 地址: {base_url}")
    print(f"  模型: {model_name}")

    # 创建 OpenAI 客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )
    
    # 构建请求参数（支持可选的 JSON mode）
    request_kwargs = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # 若指定 response_format（如 {"type": "json_object"}）则附加
    if response_format:
        request_kwargs["response_format"] = response_format

    # 调用 API
    response = client.chat.completions.create(**request_kwargs)
    
    response_text = response.choices[0].message.content
    print(f"  ✓ LLM 响应接收完成")
    
    return response_text


def parse_and_validate_json(response_text):
    """
    解析并验证 LLM 返回的 JSON
    
    参数:
        response_text: LLM 返回的文本
    
    返回:
        json_data: 解析后的 JSON 数据
    """
    print("\n正在解析 JSON...")
    
    # 尝试提取 JSON（处理可能包含 markdown 代码块的情况）
    json_str = response_text.strip()
    
    # 如果包含 ```json 标记，提取其中的内容
    if "```json" in json_str:
        json_str = json_str.split("```json")[1].split("```")[0].strip()
    elif "```" in json_str:
        json_str = json_str.split("```")[1].split("```")[0].strip()
    
    # 解析 JSON
    try:
        json_data = json.loads(json_str)
        print(f"  ✓ JSON 解析成功")
        
        # 验证 JSON 结构
        if "test_cases" not in json_data:
            print("  ⚠ 警告: JSON 缺少 'test_cases' 字段")
        
        test_cases = json_data.get("test_cases", [])
        print(f"  ✓ 包含 {len(test_cases)} 个测试用例")
        
        # 验证每个测试用例的必需字段
        required_fields = ["case_id", "test_point", "precondition", "steps", "expected_result"]
        for i, case in enumerate(test_cases):
            missing_fields = [field for field in required_fields if field not in case]
            if missing_fields:
                print(f"  ⚠ 警告: 用例 {case.get('case_id', i+1)} 缺少字段: {missing_fields}")
        
        return json_data
        
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON 解析失败: {str(e)}")
        print(f"\n原始响应:\n{response_text}")
        return None


def save_test_cases(json_data, output_file=None):
    """
    保存测试用例到文件
    
    参数:
        json_data: 测试用例 JSON 数据
        output_file: 输出文件路径
    """
    if output_file is None:
        # 自动生成文件名
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"test_cases_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n  ✓ 测试用例已保存到: {output_file}")
    return output_file


def generate_test_cases(user_requirement, vectorstore=None, top_k=3, save_to_file=True):
    """
    主函数：生成测试用例的完整流程
    
    参数:
        user_requirement: 用户的测试需求描述
        vectorstore: Chroma 向量数据库实例（如果为 None 则自动加载）
        top_k: 检索的上下文数量
        save_to_file: 是否保存到文件
    
    返回:
        json_data: 生成的测试用例 JSON 数据
    """
    print("=" * 60)
    print("测试用例自动生成器")
    print("=" * 60)
    
    # 步骤 1: 加载向量数据库
    if vectorstore is None:
        vectorstore = load_vectorstore()
    
    # 步骤 2: 检索相关上下文
    context, _ = retrieve_context(vectorstore, user_requirement, top_k)
    
    # 步骤 3: 构建 Prompt
    print("\n正在构建结构化 Prompt...")
    system_prompt, user_prompt = build_system_prompt(context, user_requirement)
    print("  ✓ Prompt 构建完成")
    
    # 步骤 4: 调用 LLM
    response_text = call_llm_api(system_prompt, user_prompt)
    
    # 步骤 5: 解析 JSON
    json_data = parse_and_validate_json(response_text)
    
    if json_data is None:
        print("\n错误: JSON 解析失败")
        return None
    
    # 步骤 6: 保存到文件
    output_file = None
    if save_to_file:
        output_file = save_test_cases(json_data)
    
    # 打印结果摘要
    print("\n" + "=" * 60)
    print("测试用例生成完成")
    print("=" * 60)
    
    test_cases = json_data.get("test_cases", [])
    print(f"\n生成的测试用例摘要:")
    for case in test_cases:
        print(f"  - {case.get('case_id', '?')}: {case.get('test_point', '?')}")
        print(f"    优先级: {case.get('priority', '?')} | 类型: {case.get('test_type', '?')}")
    
    if output_file:
        print(f"\n详细结果请查看: {output_file}")

    return json_data


# ========== API 测试用例生成（第二阶段）==========
# 基于第一阶段 parse_openapi 输出的接口结构，生成结构化测试用例 JSON
# 流程：api_spec -> RAG 检索测试规范 -> DeepSeek -> 结构化 test_cases


def _build_api_query(api_spec):
    """根据接口结构构造 RAG 检索 query"""
    method = api_spec.get("method", "")
    path = api_spec.get("path", "")
    summary = api_spec.get("summary", "")
    return (
        f"{method} {path} {summary}，"
        "请检索与参数校验、边界值、异常输入、接口测试相关的测试规范"
    )


def _build_length_boundary_rule(api_spec) -> str:
    """
    从 requestBody JSON schema 提取字符串字段的 maxLength/minLength 约束，
    生成“边界数据纪律”提示文本；无任何长度约束时返回空串。

    目的：LLM 常给 401/200 等非校验类用例随手填入超长字符串，导致请求先触发
    422、与其 expected_status 自相矛盾。显式纪律可显著降低此类无效用例。
    """
    try:
        schema = (
            api_spec.get("request_body", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        props = schema.get("properties", {})
    except AttributeError:
        return ""

    limits = []
    for name, sub in props.items():
        if not isinstance(sub, dict) or sub.get("type") != "string":
            continue
        if "maxLength" in sub or "minLength" in sub:
            limits.append((name, sub.get("minLength"), sub.get("maxLength")))

    if not limits:
        return ""

    desc = "、".join(
        f"{name} 上限 {mx}" + (f"、下限 {mn}" if mn is not None else "")
        for name, mn, mx in limits
    )
    return (
        "7. 长度边界数据纪律（requestBody 字符串字段约束：" + desc + "）：\n"
        "   - 只有专门验证“超长/越界被拒”的 boundary 用例，才允许把该字段设为越过上限的值，"
        "且其 expected_status 必须为 422；\n"
        "   - 其余所有用例（normal=200、鉴权失败=401 等非校验类场景），字符串字段必须严格处在"
        "长度上限内；构造错误凭据时使用普通长度的错误值（例如 wrongpass），严禁使用超长字符串；\n"
        "   - 否则请求会先触发 422，与该用例声明的预期状态自相矛盾，判为无效用例。\n"
    )


def _build_api_system_prompt(api_spec, rag_context, rag_used):
    """构建 API 测试用例生成的 System Prompt"""
    api_json = json.dumps(api_spec, ensure_ascii=False, indent=2)
    if rag_used and rag_context:
        rag_section = rag_context
    else:
        rag_section = "（未检索到相关测试规范，请基于下方 API Schema 设计）"

    path = api_spec.get("path", "")
    method = api_spec.get("method", "")
    summary = api_spec.get("summary", "")

    # 从 requestBody schema 提取字符串字段长度约束，动态生成“边界数据纪律”，
    # 防止 LLM 给非校验类用例（如 401/200）误用超长字符串而先触发 422。
    length_rule = _build_length_boundary_rule(api_spec)

    return f"""你是一名资深 API 测试工程师，精通等价类划分、边界值分析与异常场景设计。

## 当前 API Schema
{api_json}

## 参考测试规范（RAG 检索）
{rag_section}

## 测试设计原则
1. 优先采用等价类划分、边界值分析、异常场景分析
2. 只针对 Schema 中实际存在的参数（path/query/header/body）设计测试
3. 禁止虚构接口 Schema 中不存在的参数或业务规则
4. 预期成功（2xx）的正常用例，其请求取值必须使用 requestBody schema 的 example，
   不得自行编造能登录/操作成功的凭据；接口文档若给出唯一合法凭据，必须原样使用
5. 严格按接口文档区分状态码：文档明确为鉴权失败（如 401）与参数校验失败（如 422）
   的场景不得混淆；expected_status 必须符合文档描述的真实契约
6. 覆盖以下场景（按 Schema 适用性选择，不适用则跳过）：
   - 正常场景
   - 必填参数缺失
   - 空值
   - 参数类型错误
   - 边界值
   - 非法值
   - 路径参数异常（仅当存在 path 参数）
   - Query 参数异常（仅当存在 query 参数）
   - Body 参数异常（仅当存在 requestBody）
   - 鉴权异常（仅当 Schema 表明涉及认证时）
{length_rule}
## 输出格式（必须严格遵守）
- 只输出合法 JSON，禁止输出 Markdown 代码块（不要使用 ``` 包裹）
- 禁止输出任何 JSON 以外的说明文字
- JSON 结构如下：
{{
  "api": "{path}",
  "method": "{method}",
  "summary": "{summary}",
  "test_cases": [
    {{
      "case_id": "前缀_001",
      "title": "用例标题",
      "test_point": "测试点",
      "test_type": "normal|boundary|exception",
      "priority": "P0|P1|P2",
      "request": {{
        "path_params": {{}},
        "query_params": {{}},
        "headers": {{}},
        "body": {{}}
      }},
      "expected_status": 200,
      "expected_result": "预期结果"
    }}
  ]
}}

## 字段约束
- test_type 只能取：normal、boundary、exception
- priority 只能取：P0、P1、P2
- 至少生成 5 条测试用例
"""


def _build_api_user_prompt(api_spec):
    """构建 API 测试用例生成的 User Prompt"""
    method = api_spec.get("method", "")
    path = api_spec.get("path", "")
    summary = api_spec.get("summary", "")
    return (
        f"请基于上述 API Schema 与测试规范，为该接口生成结构化测试用例 JSON。\n\n"
        f"接口：{method} {path} - {summary}\n\n"
        "只输出 JSON。"
    )


def _parse_api_response_json(response_text):
    """解析 LLM 返回的 JSON（剥离可能的 Markdown 代码块）"""
    if not response_text:
        return None
    json_str = response_text.strip()
    # 兼容模型仍然包裹 ```json 或 ``` 的情况
    if "```json" in json_str:
        parts = json_str.split("```json")
        if len(parts) > 1:
            json_str = parts[1].split("```")[0].strip()
    elif "```" in json_str:
        parts = json_str.split("```")
        if len(parts) > 1:
            json_str = parts[1].split("```")[0].strip()
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  ✗ JSON 解析失败: {e}")
        return None


def _validate_api_cases(data, api_spec):
    """校验生成的测试用例结构是否符合规范"""
    if not isinstance(data, dict):
        return False
    if "test_cases" not in data or not isinstance(data["test_cases"], list):
        print("  ⚠ 缺少 test_cases 列表")
        return False
    if not data["test_cases"]:
        print("  ⚠ test_cases 为空")
        return False

    required_fields = [
        "case_id", "title", "test_type", "priority",
        "request", "expected_status", "expected_result",
    ]
    valid_types = {"normal", "boundary", "exception"}
    valid_priorities = {"P0", "P1", "P2"}

    for i, case in enumerate(data["test_cases"], 1):
        if not isinstance(case, dict):
            print(f"  ⚠ 用例 {i} 不是 dict")
            return False
        for f in required_fields:
            if f not in case:
                print(f"  ⚠ 用例 {i} 缺少字段: {f}")
                return False
        # 值合法性软警告（不阻断，避免真实模型偶发越界导致整体失败）
        if case.get("test_type") not in valid_types:
            print(f"  ⚠ 用例 {i} test_type 非常规值: {case.get('test_type')}")
        if case.get("priority") not in valid_priorities:
            print(f"  ⚠ 用例 {i} priority 非常规值: {case.get('priority')}")

    return True


def _string_field_limits(api_spec, where="body"):
    """提取 requestBody(where='body') 或 parameters(where='query'/'path') 中
    字符串字段的长度约束，返回 {字段名: {"min": int|None, "max": int|None}}。
    结构缺失时返回空 dict，绝不抛异常（容错解析）。"""
    limits = {}
    try:
        if where == "body":
            props = (
                api_spec.get("request_body", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("properties", {})
            )
        else:
            props = {}
            for p in api_spec.get("parameters", []) or []:
                if p.get("in") == where and isinstance(p, dict):
                    props[p.get("name")] = p.get("schema", {})
        for name, sub in props.items():
            if isinstance(sub, dict) and sub.get("type") == "string" and (
                "maxLength" in sub or "minLength" in sub
            ):
                limits[name] = {
                    "min": sub.get("minLength"),
                    "max": sub.get("maxLength"),
                }
    except (AttributeError, TypeError):
        return {}
    return limits


def find_contract_conflicts(case, api_spec):
    """
    判定单条 LLM 用例的 request 是否与其 expected_status 存在【可客观证明】的矛盾。

    保守规则（只报可证明的无效用例，避免掩盖真实 API 缺陷）：
    - body/query/path 中某字符串字段的实际长度越过 OpenAPI 声明的 minLength/maxLength；
    - 而 expected_status 不是 422（越界本应被参数校验拦截为 422，无法到达 401/200）。

    典型反例（LLM 高频错误）：为 401 鉴权失败用例填入 140 字符密码，而 schema 声明
    maxLength=128 —— 该请求必然先得到 422，预期 401 不成立。

    返回：矛盾说明字符串列表（空列表表示无矛盾）。
    """
    conflicts = []
    if not isinstance(case, dict) or not isinstance(api_spec, dict):
        return conflicts

    expected = case.get("expected_status")
    # 422 用例本就预期参数校验失败，越界数据是其正确测试手段，不构成矛盾
    if expected == 422:
        return conflicts

    req = case.get("request")
    if not isinstance(req, dict):
        return conflicts

    sources = (
        ("body", req.get("body")),
        ("query", req.get("query_params")),
        ("path", req.get("path_params")),
    )
    for where, values in sources:
        if not isinstance(values, dict):
            continue
        limits = _string_field_limits(api_spec, where)
        for field, val in values.items():
            bound = limits.get(field)
            if not bound or not isinstance(val, str):
                continue
            n = len(val)
            if bound["max"] is not None and n > bound["max"]:
                conflicts.append(
                    f"{where}.{field} 长度 {n} 超过 maxLength={bound['max']}，"
                    f"该请求必触发 422，与 expected_status={expected} 矛盾"
                )
            elif bound["min"] is not None and n < bound["min"]:
                conflicts.append(
                    f"{where}.{field} 长度 {n} 小于 minLength={bound['min']}，"
                    f"该请求必触发 422，与 expected_status={expected} 矛盾"
                )
    return conflicts


def generate_test_cases_from_api(api_spec, top_k=3, vectorstore=None, llm_call=None):
    """
    根据接口结构（第一阶段输出）生成结构化测试用例

    流程：api_spec -> RAG 检索测试规范 -> DeepSeek -> 结构化 test_cases JSON

    参数:
        api_spec: 第一阶段 parse_openapi 返回的单个接口 dict，需含 path/method
        top_k: RAG 检索的上下文数量
        vectorstore: 向量库实例（None 则自动加载；加载失败降级为 api_spec + LLM）
        llm_call: 可注入的 LLM 调用函数（用于测试 mock），签名
                  (system_prompt, user_prompt, **kwargs) -> str；None 则用 call_llm_api

    返回:
        结构化测试用例 dict（含 api/method/summary/test_cases），失败返回 None
    """
    if not isinstance(api_spec, dict) or "path" not in api_spec or "method" not in api_spec:
        raise ValueError("api_spec 必须是 dict 且包含 path 与 method 字段")

    if llm_call is None:
        llm_call = call_llm_api

    print("=" * 60)
    print("API 测试用例生成器")
    print("=" * 60)

    path = api_spec.get("path", "")
    method = api_spec.get("method", "")
    summary = api_spec.get("summary", "")
    print(f"  接口: {method} {path} - {summary}")

    # 步骤 1: 构造检索 query
    query = _build_api_query(api_spec)

    # 步骤 2: RAG 检索（降级容错：失败不阻断生成）
    rag_context = ""
    rag_used = False
    try:
        vs = vectorstore if vectorstore is not None else load_vectorstore()
        rag_context, _ = retrieve_context(vs, query, top_k)
        rag_used = True
    except Exception as e:
        print(f"  ⚠ RAG 检索失败，降级为 api_spec + LLM: {e}")
        rag_context = ""
        rag_used = False

    # 步骤 3: 构建 Prompt
    system_prompt = _build_api_system_prompt(api_spec, rag_context, rag_used)
    user_prompt = _build_api_user_prompt(api_spec)
    print("  ✓ Prompt 构建完成")

    # 步骤 4: 调用 LLM（JSON mode + 低 temperature）
    llm_kwargs = {
        "temperature": config.LLM_TEMPERATURE_CASES,
        "max_tokens": config.LLM_MAX_TOKENS_CASES,
        "response_format": {"type": "json_object"},
    }

    def _safe_call(sp, up):
        try:
            return llm_call(sp, up, **llm_kwargs)
        except TypeError:
            # llm_call 不支持 response_format 等参数，退回基础调用
            return llm_call(sp, up)

    response_text = _safe_call(system_prompt, user_prompt)

    # 步骤 5: 解析 + 校验
    data = _parse_api_response_json(response_text)
    valid = _validate_api_cases(data, api_spec) if data else False

    # 步骤 6: 失败重试 1 次（明确要求只返回合法 JSON）
    if not valid:
        print("  ⚠ 首次解析/校验失败，重试 1 次...")
        retry_prompt = "上一次输出无法解析，请仅返回合法 JSON，不要包含任何 Markdown 代码块或额外说明。"
        response_text = _safe_call(system_prompt, retry_prompt)
        data = _parse_api_response_json(response_text)
        valid = _validate_api_cases(data, api_spec) if data else False

    if not valid:
        print("  ✗ 测试用例生成失败")
        return None

    # 补全顶层字段，确保与 api_spec 一致
    data["api"] = path
    data["method"] = method
    data.setdefault("summary", summary)

    print(f"  ✓ 生成 {len(data.get('test_cases', []))} 条测试用例")
    return data


def main():
    """
    主函数：演示测试用例生成器的使用
    """
    
    # 测试用例示例
    test_requirements = [
        "登录接口，包含用户名和密码",
        "文件上传功能，支持 JPG 和 PNG 格式，最大 5MB",
        "用户注册功能，需要邮箱验证，密码要求至少8位包含大小写字母和数字"
    ]
    
    # 生成第一个测试用例
    requirement = test_requirements[0]
    print(f"\n需求: {requirement}\n")
    
    try:
        result = generate_test_cases(requirement)
        
        if result:
            print("\n\n完整 JSON 输出:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
    except Exception as e:
        print(f"\n错误: {str(e)}")
        print("\n请确保已设置环境变量:")
        print("  - OPENAI_API_KEY: 你的 API 密钥")
        print("  - OPENAI_BASE_URL: API 地址（可选，默认 OpenAI）")
        print("  - MODEL_NAME: 模型名称（可选，默认 gpt-3.5-turbo）")
        print("\n示例（使用 DeepSeek）:")
        print("  set OPENAI_API_KEY=your-api-key")
        print("  set OPENAI_BASE_URL=https://api.deepseek.com/v1")
        print("  set MODEL_NAME=deepseek-chat")


if __name__ == "__main__":
    main()
