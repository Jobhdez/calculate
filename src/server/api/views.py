from django.shortcuts import render
from src.interpreter.parser import parser
from src.interpreter.interpreter import evaluate
from .forms import (
    UserRegistrationForm,
    LoginForm,
    RequestFriendForm,
    AcceptForm,
    LinearAlgebraExpForm,
    JoinBookStudyForm,
    StudyForm,
    )
from .models import FriendRequest, LinearAlgebraExpression, BookStudy
from django.contrib.auth import (
    authenticate,
    login,
    get_user_model,
    )
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from .serializers import LinearAlgebraExpSerializer
from actions.utils import create_action
from django.core import serializers
from actions.models import Action
from .tasks import friend_request_sent
from .recommender import Recommender
from django.core.cache import cache
import hashlib
User = get_user_model()

"""Module includes endpoints for a small social media back-end :-)
;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;;
"""
@api_view(['POST'])
def register(request):
    """View that allows the given user register."""
    form = UserRegistrationForm(request.POST)
    if form.is_valid():
        new_user = form.save(commit=False)
        data = form.cleaned_data
        new_user.set_password(data['password'])
        new_user.save()
        create_action(new_user, 'has created an account')
        return Response({'account': 'created'})
    return Response({'form': 'invalid'})


@api_view(['POST'])
def user_login(request):
    form = LoginForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        username = data['username']
        password = data['password']
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return Response({'login': 'Succesful'}) # should I respond with a status error?
        return Response({'Invalid': 'login'}) ## respond with a status error?
    return Response({'form': 'invalid'})

@api_view(['POST'])
@login_required(login_url='/api/login/')
@csrf_exempt
def request_friend(request):
    form = RequestFriendForm(request.POST)
    if form.is_valid():
        cd = form.cleaned_data  
        from_user = request.user
        to_user = User.objects.get(username=cd['username'])
        friend_request, created = FriendRequest.objects.get_or_create(from_user=from_user, to_user=to_user)
        from_user_username = from_user.username
        to_user_username = to_user.username
        friend_request_sent.delay(from_user_username, to_user_username)
        if created:
            return Response({'request': 'sent'})
        return Response({'request': 'was sent already'})

@api_view(['POST'])
@login_required(login_url='/api/login/')
@csrf_exempt
def accept_friend_request(request):
    form = AcceptForm(request.POST)
    if form.is_valid():
        cd = form.cleaned_data
        accepted_user = User.objects.get(username=cd['username'])
        friend_request = FriendRequest.objects.get(from_user=accepted_user, to_user=request.user)
        if friend_request.to_user == request.user:
            friend_request.to_user.friends.add(friend_request.from_user)
            friend_request.from_user.friends.add(friend_request.to_user)
            create_action(request.user, 'is friends with', accepted_user)
            friend_request.delete()
            return Response({"accept": "request"})
        return Response({"request":"not accepted"})

@api_view(['POST'])
@login_required(login_url='/api/login/')
@csrf_exempt
def compute_lalg_expression(request):
    def list_to_string(lst):
      return '[' + ' '.join(map(str, lst)) + ']'
    
    form = LinearAlgebraExpForm(request.POST)
    if form.is_valid():
        new_expr = form.save(commit=False)
        data_expr = form.cleaned_data
        data_expr = data_expr['exp']
        exp_hash = hashlib.md5(data_expr.encode()).hexdigest()
        #alg_exp = cache.get(exp_hash)
        #if not alg_exp:
        parsed_exp = parser.parse(data_expr)
        eval_data = evaluate(parsed_exp)
        eval_data = list_to_string(eval_data)
        expr_model = LinearAlgebraExpression(exp=eval_data)
        expr_model.save()
        create_action(request.user, 'computed an expression', expr_model)
        serializer = LinearAlgebraExpSerializer(expr_model)
        #    cache.set(exp_hash, serializer.data)
        return Response(serializer.data)
     #   return Response(alg_exp)
    return Response({"form": "invalid"})
  
@login_required
def dashboard(request):
    actions = Action.objects.exclude(user=request.user)
    friends_id = request.user.friends.values_list('id', flat=True)

    if friends_id:
        actions = actions.filter(user_id__in=friends_id)

    actions = actions[:10]
    data = serializers.serialize('json', actions)
    

    return Response({'actions': data})

@api_view(['GET'])
@login_required
def list_linear_algebra_exps(request):
    exps = LinearAlgebraExpression.objects.all()
    data = LinearAlgebraExpSerializer(exps, many=True)

    return Response({'expressions': data})

@api_view(['GET'])
@login_required
def linear_algebra_exp_detail(request, id):
    exp = LinearAlgebraExpression.objects.get(id=id)

    r = Recommender()
    recommended_expressions = r.suggest_expressions_for([exp], 4)
    data = serializers.serialize('json', recommended_expressions)
    return Response({'expression': data})

@api_view(['POST'])
@login_required
def join_book_study(request):
    form = JoinBookStudyForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        from_user = request.user
        to_user = data['to_user']
        to_user = User.objects.get(username=to_user)
        if from_user in to_user.friends.all():
            book_study = BookStudy.objects.get(name=data['study_name'])
            book_study.members.add(from_user)
            return Response({'joined': "book study"})
        return Response({"not joined": "send a friend request first"})
    return Response({"form": "invalid"})


@api_view(['POST'])
@login_required
def create_study(request):
    form = StudyForm(request.POST)
    if form.is_valid():
        data = form.cleaned_data
        usr = request.user
        book_study = BookStudy.objects.create(owner=usr, name=data['name'])
        usr.study_groups.add(book_study)
        return Response({'study group': 'created'})
    return Response({'form': 'invalid'})

                                
