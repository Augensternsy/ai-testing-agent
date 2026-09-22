# -*- coding: utf-8 -*-
"""
RAG 向量知识库构建脚本

功能说明：
1. 读取本地目录 ./docs 下所有的 Markdown 或 TXT 文件
2. 使用 RecursiveCharacterTextSplitter 对文档进行切片（Chunking）
3. 使用开源的 Embedding 模型将文本向量化
4. 将向量数据持久化保存到本地的 Chroma 向量数据库中

依赖安装：
pip install langchain langchain-community langchain-text-splitters chromadb sentence-transformers
"""

import os
import glob
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma


def load_documents_from_directory(directory_path):
    """
    从指定目录加载所有 Markdown 和 TXT 文件
    
    参数:
        directory_path: 文档目录路径
    
    返回:
        documents: 加载的文档列表
    """
    documents = []
    
    # 查找所有 .md 和 .txt 文件
    file_patterns = [
        os.path.join(directory_path, "**/*.md"),
        os.path.join(directory_path, "**/*.txt")
    ]
    
    file_paths = []
    for pattern in file_patterns:
        file_paths.extend(glob.glob(pattern, recursive=True))
    
    if not file_paths:
        print(f"警告: 在目录 {directory_path} 中未找到任何 .md 或 .txt 文件")
        return documents
    
    print(f"找到 {len(file_paths)} 个文档文件")
    
    # 逐个加载文档
    for file_path in file_paths:
        try:
            # 使用 UTF-8 编码加载文档
            loader = TextLoader(file_path, encoding='utf-8')
            docs = loader.load()
            
            # 为每个文档添加元数据（文件名）
            for doc in docs:
                doc.metadata['source_file'] = os.path.basename(file_path)
            
            documents.extend(docs)
            print(f"  ✓ 已加载: {os.path.basename(file_path)}")
            
        except Exception as e:
            print(f"  ✗ 加载失败 {file_path}: {str(e)}")
    
    print(f"\n成功加载 {len(documents)} 个文档\n")
    return documents


def split_documents(documents, chunk_size=500, chunk_overlap=50):
    """
    使用 RecursiveCharacterTextSplitter 对文档进行切片
    
    参数:
        documents: 待切分的文档列表
        chunk_size: 每个文本块的大小（字符数）
        chunk_overlap: 文本块之间的重叠字符数
    
    返回:
        chunks: 切分后的文本块列表
    """
    print(f"开始文档切片...")
    print(f"  切片大小: {chunk_size} 字符")
    print(f"  重叠大小: {chunk_overlap} 字符")
    
    # 创建文本切片器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", "。", "，", " ", ""]  # 支持中英文分隔符
    )
    
    # 执行切片
    chunks = text_splitter.split_documents(documents)
    
    print(f"  ✓ 切片完成，共生成 {len(chunks)} 个文本块\n")
    return chunks


def create_embeddings():
    """
    创建 HuggingFace BGE Embedding 模型
    
    返回:
        embeddings: Embedding 模型实例
    """
    print("正在加载 Embedding 模型...")
    
    # 使用 BGE (BAAI General Embedding) 模型
    # 这是一个开源的高质量中文 Embedding 模型
    model_name = "BAAI/bge-base-zh-v1.5"
    
    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={'device': 'cpu'},  # 如果有 GPU 可以改为 'cuda'
        encode_kwargs={'normalize_embeddings': True}
    )
    
    print(f"  ✓ Embedding 模型加载成功: {model_name}\n")
    return embeddings


def save_to_chroma(chunks, embeddings, persist_directory="./chroma_db"):
    """
    将文本块和向量保存到 Chroma 向量数据库
    
    参数:
        chunks: 文本块列表
        embeddings: Embedding 模型
        persist_directory: 数据库持久化目录
    """
    print(f"正在构建向量数据库...")
    print(f"  持久化目录: {persist_directory}")
    
    # 如果数据库已存在，先删除
    if os.path.exists(persist_directory):
        print(f"  检测到已存在的数据库，正在清理...")
    
    # 创建 Chroma 向量数据库
    # from_documents 会自动调用 embeddings 将文本转换为向量
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=persist_directory
    )
    
    # 持久化保存到磁盘
    vectorstore.persist()
    
    print(f"  ✓ 向量数据库构建完成并保存\n")
    return vectorstore


def test_retrieval(vectorstore, query="软件测试的基本要求是什么？"):
    """
    测试向量检索功能
    
    参数:
        vectorstore: 向量数据库实例
        query: 测试查询文本
    """
    print(f"测试检索功能...")
    print(f"  查询: {query}\n")
    
    # 执行相似度检索
    results = vectorstore.similarity_search(query, k=3)
    
    print(f"找到 {len(results)} 个相关结果:\n")
    for i, result in enumerate(results, 1):
        print(f"--- 结果 {i} ---")
        print(f"来源文件: {result.metadata.get('source_file', '未知')}")
        print(f"内容预览: {result.page_content[:200]}...")
        print(f"\n")


def main():
    """
    主函数：执行完整的 RAG 知识库构建流程
    """
    print("=" * 60)
    print("RAG 向量知识库构建系统")
    print("=" * 60)
    print()
    
    # 配置参数
    docs_directory = "./docs"  # 文档目录
    persist_directory = "./chroma_db"  # 向量数据库保存目录
    chunk_size = 500  # 文本块大小
    chunk_overlap = 50  # 文本块重叠
    
    # 步骤 1: 加载文档
    print("[步骤 1/4] 加载文档")
    print("-" * 60)
    documents = load_documents_from_directory(docs_directory)
    
    if not documents:
        print("错误: 未找到任何文档，程序退出")
        return
    
    # 步骤 2: 文档切片
    print("[步骤 2/4] 文档切片")
    print("-" * 60)
    chunks = split_documents(documents, chunk_size, chunk_overlap)
    
    # 步骤 3: 创建 Embedding 模型
    print("[步骤 3/4] 加载 Embedding 模型")
    print("-" * 60)
    embeddings = create_embeddings()
    
    # 步骤 4: 构建并保存向量数据库
    print("[步骤 4/4] 构建向量数据库")
    print("-" * 60)
    vectorstore = save_to_chroma(chunks, embeddings, persist_directory)
    
    # 测试检索功能
    print("=" * 60)
    print("检索功能测试")
    print("=" * 60)
    print()
    
    # 测试查询示例
    test_queries = [
        "软件测试的基本要求是什么？",
        "测试流程包括哪些阶段？",
        "如何进行性能测试？",
        "自动化测试的适用范围是什么？"
    ]
    
    for query in test_queries:
        test_retrieval(vectorstore, query)
    
    print("=" * 60)
    print("RAG 向量知识库构建完成！")
    print("=" * 60)
    print(f"\n数据库已保存到: {persist_directory}")
    print("\n后续使用示例：")
    print("""
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# 加载已保存的向量数据库
embeddings = HuggingFaceEmbeddings(
    model_name="BAAI/bge-base-zh-v1.5",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True},
)
vectorstore = Chroma(
    persist_directory="./chroma_db",
    embedding_function=embeddings
)

# 执行检索
results = vectorstore.similarity_search("你的问题")
""")


if __name__ == "__main__":
    main()
