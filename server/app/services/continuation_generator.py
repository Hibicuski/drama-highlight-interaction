from app.db.models import ContinuationRequest, ContinuationResponse
from app.services.model_client import ModelClient


def generate_continuation(request: ContinuationRequest) -> ContinuationResponse:
    model_client = ModelClient()

    if not model_client.is_configured:
        return ContinuationResponse(
            title="剧情续写卡",
            content=f"你选择了「{request.choice}」。下一幕里，主角没有立刻退让，而是顺着线索反击，把刚才的高光推进到新的冲突点。",
        )

    # The real model prompt will be wired after MVP verification.
    return ContinuationResponse(
        title="剧情续写卡",
        content=f"你选择了「{request.choice}」。模型接入将在下一阶段替换这里的占位结果。",
    )
