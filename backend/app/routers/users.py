from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AuditEventType, Subscription, User
from app.schemas import DeleteResult, SubscriptionRead, UserCreate, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.post("", response_model=UserRead)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    user = User(**payload.model_dump())
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("", response_model=list[UserRead])
def list_users(q: str | None = Query(default=None), db: Session = Depends(get_db)):
    query = db.query(User)
    if q:
        like = f"%{q}%"
        query = query.filter((User.name.ilike(like)) | (User.email.ilike(like)) | (User.telegram_id.ilike(like)) | (User.external_id.ilike(like)))
    return query.order_by(User.created_at.desc()).all()


@router.get("/{user_id}", response_model=UserRead)
def read_user(user_id: str, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
def patch_user(user_id: str, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.external_id_set:
        user.external_id = payload.external_id
    if payload.name_set:
        user.name = payload.name
    if payload.email_set:
        user.email = payload.email
    if payload.telegram_id_set:
        user.telegram_id = payload.telegram_id
    if payload.status is not None:
        user.status = payload.status
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}/subscriptions", response_model=list[SubscriptionRead])
def list_user_subscriptions(user_id: str, db: Session = Depends(get_db)):
    if not db.get(User, user_id):
        raise HTTPException(status_code=404, detail="User not found")
    return db.query(Subscription).filter(Subscription.user_id == user_id).order_by(Subscription.created_at.desc()).all()


@router.delete("/{user_id}", response_model=DeleteResult)
def delete_user(user_id: str, force: bool = Query(default=False), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    subscriptions = db.query(Subscription).filter(Subscription.user_id == user_id).all()
    if subscriptions and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "User has subscriptions. Pass force=true to delete the user and all local subscription records.",
                "subscriptions": len(subscriptions),
            },
        )

    deleted_subscriptions = len(subscriptions)
    for subscription in subscriptions:
        db.delete(subscription)

    db.delete(user)
    from app.services.audit import audit
    audit(
        db,
        AuditEventType.subscription_updated,
        f"User {user_id} deleted",
        entity_type="user",
        entity_id=user_id,
        payload={"force": force, "deleted_subscriptions": deleted_subscriptions},
    )
    db.commit()
    return DeleteResult(deleted=True, entity_type="user", entity_id=user_id, deleted_children={"subscriptions": deleted_subscriptions})
