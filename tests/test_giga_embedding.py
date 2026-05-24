import torch
from sentence_transformers import SentenceTransformer


MODEL_NAME = "ai-sage/Giga-Embeddings-instruct"


def main():
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model_kwargs = {
        "trust_remote_code": True,
    }

    if device == "cuda":
        major, _ = torch.cuda.get_device_capability(0)

        if major >= 8:
            model_kwargs["torch_dtype"] = torch.bfloat16
        else:
            model_kwargs["torch_dtype"] = torch.float16

    model = SentenceTransformer(
        MODEL_NAME,
        model_kwargs=model_kwargs,
        config_kwargs={"trust_remote_code": True},
        device=device,
    )

    task = (
        "Дан вопрос пользователя, необходимо найти среди фрагментов "
        "расшифровок и саммари встреч релевантный фрагмент с ответом"
    )

    query = "Что обсуждали на созвоне про переводчиков?"

    docs = [
        "Основное — это общение с переводчиками, потом чат-боты для обучения и чат-боты для переводчиков тоже.",
        "Обсуждали технические проблемы с SSL-сертификатом при публикации в CS-Cart.",
        "Говорили про закупку офисной мебели и ремонт переговорной.",
    ]

    # query_prompt = f"Instruct: {task}\nQuery: "

    q_emb = model.encode(
        [query],
        # prompt=query_prompt,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    d_emb = model.encode(
        docs,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    scores = d_emb @ q_emb[0]

    for doc, score in sorted(zip(docs, scores), key=lambda x: x[1], reverse=True):
        print(round(float(score), 4), doc)

    print("Embedding shape:", q_emb.shape)


if __name__ == "__main__":
    main()