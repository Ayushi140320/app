import pyotp
from flask import jsonify, request
from flask_cors import cross_origin
from itsdangerous import Signer, BadSignature

from app.api.base import api_bp
from app.config import FLASK_SECRET
from app.extensions import db
from app.log import LOG
from app.models import User, ApiKey


@api_bp.route("/auth/mfa", methods=["POST"])
@cross_origin()
def auth_mfa():
    """
    Validate the OTP Token
    Input:
        mfa_token: OTP token that user enters
        mfa_key: MFA key obtained in previous auth request, e.g. /api/auth/login
        device: the device name, used to create an ApiKey associated with this device
    Output:
        200 and user info containing:
        {
            name: "John Wick",
            api_key: "a long string"
        }

    """
    data = request.get_json()
    if not data:
        return jsonify(error="request body cannot be empty"), 400

    mfa_token = data.get("mfa_token")
    mfa_key = data.get("mfa_key")
    device = data.get("device")

    s = Signer(FLASK_SECRET)
    try:
        user_id = int(s.unsign(mfa_key))
    except BadSignature:
        return jsonify(error="Invalid mfa_key"), 400

    user = User.get(user_id)

    if not user:
        return jsonify(error="Invalid mfa_key"), 400
    elif not user.enable_otp:
        return (
            jsonify(error="This endpoint should only be used by user who enables MFA"),
            400,
        )

    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(mfa_token):
        return jsonify(error="Wrong TOTP Token"), 400

    ret = {"name": user.name}

    api_key = ApiKey.get_by(user_id=user.id, name=device)
    if not api_key:
        LOG.d("create new api key for %s and %s", user, device)
        api_key = ApiKey.create(user.id, device)
        db.session.commit()

    ret["api_key"] = api_key.code

    return jsonify(**ret), 200
