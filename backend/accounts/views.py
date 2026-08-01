from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.conf import settings
from django.contrib.auth import update_session_auth_hash
from core.permissions import IsAdmin
from .models import User
from .serializers import (
    UserSerializer, AdminUserSerializer, RegisterSerializer, LoginSerializer,
    ChangePasswordSerializer, ForgotPasswordSerializer, ResetPasswordSerializer
)
import uuid

class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'message': 'Registration successful',
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            refresh = RefreshToken.for_user(user)
            return Response({
                'message': 'Login successful',
                'user': UserSerializer(user).data,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist() if hasattr(token, 'blacklist') else None
        except Exception:
            pass
        return Response({'message': 'Logged out successfully'})

class ProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)

    def put(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'Profile updated', 'user': serializer.data})
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ProfilePhotoView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if 'profile_photo' not in request.FILES:
            return Response({'error': 'No photo provided'}, status=400)
        request.user.profile_photo = request.FILES['profile_photo']
        request.user.save()
        return Response({'message': 'Photo updated', 'photo': request.build_absolute_uri(request.user.profile_photo.url)})

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            if not user.check_password(serializer.validated_data['old_password']):
                return Response({'error': 'Current password is incorrect'}, status=400)
            user.set_password(serializer.validated_data['new_password'])
            user.save()
            return Response({'message': 'Password changed successfully'})
        return Response(serializer.errors, status=400)

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        if serializer.is_valid():
            email = serializer.validated_data['email']
            try:
                user = User.objects.get(email=email)
                token = str(uuid.uuid4())
                user.reset_token = token
                user.save()
                # TODO: wire up real email delivery before going to production.
                # The token is only echoed back while DEBUG=True so local
                # dev/testing works without SMTP; in production, echoing it
                # would let anyone reset any account just by knowing its email.
                if settings.DEBUG:
                    return Response({'message': 'Reset token generated', 'reset_token': token, 'note': 'DEBUG mode only: token returned directly instead of emailed'})
                return Response({'message': 'If that email exists, a reset link has been sent.'})
            except User.DoesNotExist:
                # Same response as success: don't reveal whether an email
                # is registered (avoids account enumeration).
                return Response({'message': 'If that email exists, a reset link has been sent.'})
        return Response(serializer.errors, status=400)

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        if serializer.is_valid():
            token = serializer.validated_data['token']
            new_password = serializer.validated_data['new_password']
            try:
                user = User.objects.get(reset_token=token)
                user.set_password(new_password)
                user.reset_token = None
                user.save()
                return Response({'message': 'Password reset successful'})
            except User.DoesNotExist:
                return Response({'error': 'Invalid or expired token'}, status=400)
        return Response(serializer.errors, status=400)

class AdminUserListView(generics.ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]
    queryset = User.objects.all().order_by('-date_joined')


class AdminUserDetailView(generics.RetrieveUpdateDestroyAPIView):
    # Previously GET (retrieve) had no role check at all - any authenticated
    # user could fetch any other user's full profile just by guessing an id.
    # A single class-level permission now covers GET/PUT/PATCH/DELETE.
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]
    queryset = User.objects.all()
