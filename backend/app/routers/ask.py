from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import DB, AppSettings, CurrentUser, get_embedder, get_llm
from app.providers import LLM, Embedder
from app.rag import Answer, answer_question
from app.schemas import AskIn, AskOut

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskOut)
def ask(
    body: AskIn,
    user: CurrentUser,
    db: DB,
    settings: AppSettings,
    embedder: Annotated[Embedder, Depends(get_embedder)],
    llm: Annotated[LLM, Depends(get_llm)],
) -> Answer:
    return answer_question(db, user, body.question, embedder=embedder, llm=llm, settings=settings)
