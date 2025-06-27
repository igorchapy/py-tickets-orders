from rest_framework import viewsets

from cinema.models import Genre, Actor, CinemaHall, Movie, MovieSession

from cinema.serializers import (
    GenreSerializer,
    ActorSerializer,
    CinemaHallSerializer,
    MovieSerializer,
    MovieSessionSerializer,
    MovieSessionListSerializer,
    MovieDetailSerializer,
    MovieSessionDetailSerializer,
    MovieListSerializer,
)


class GenreViewSet(viewsets.ModelViewSet):
    queryset = Genre.objects.all()
    serializer_class = GenreSerializer


class ActorViewSet(viewsets.ModelViewSet):
    queryset = Actor.objects.all()
    serializer_class = ActorSerializer


class CinemaHallViewSet(viewsets.ModelViewSet):
    queryset = CinemaHall.objects.all()
    serializer_class = CinemaHallSerializer


class MovieViewSet(viewsets.ModelViewSet):
    queryset = Movie.objects.all()
    serializer_class = MovieSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return MovieListSerializer

        if self.action == "retrieve":
            return MovieDetailSerializer

        return MovieSerializer


class MovieSessionViewSet(viewsets.ModelViewSet):
    queryset = MovieSession.objects.all()
    serializer_class = MovieSessionSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return MovieSessionListSerializer

        if self.action == "retrieve":
            return MovieSessionDetailSerializer

        return MovieSessionSerializer

class MovieDetailSerializer(MovieSerializer):
    genres = GenreSerializer(many=True, read_only=True)
    actors = ActorSerializer(many=True, read_only=True)
    class Meta:
        model = Movie
        fields = ("id", "title", "description", "duration", "genres", "actors")
class MovieSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MovieSession
        fields = ("id", "show_time", "movie", "cinema_hall")
class MovieSessionListSerializer(MovieSessionSerializer):
    movie_title = serializers.CharField(source="movie.title", read_only=True)
    cinema_hall_name = serializers.CharField(
        source="cinema_hall.name", read_only=True
    )
    cinema_hall_capacity = serializers.IntegerField(
        source="cinema_hall.capacity", read_only=True
    )
    tickets_available = serializers.SerializerMethodField()

    class Meta:
        model = MovieSession
        fields = (
            "id",
            "show_time",
            "movie_title",
            "cinema_hall_name",
            "cinema_hall_capacity",
            "tickets_available"
        )

    def get_tickets_available(self, obj):
        return obj.cinema_hall.capacity - obj.tickets.count()


class MovieSessionDetailSerializer(MovieSessionSerializer):
    movie = MovieListSerializer(many=False, read_only=True)
    cinema_hall = CinemaHallSerializer(many=False, read_only=True)
    taken_places = serializers.SerializerMethodField()

    class Meta:
        model = MovieSession
        fields = ("id", "show_time", "movie", "cinema_hall")
        fields = ("id", "show_time", "movie", "cinema_hall", "taken_places")

    def get_taken_places(self, obj):
        return [
            {"row": ticket.row, "seat": ticket.seat}
            for ticket in obj.tickets.all()
        ]


class TicketSerializer(serializers.ModelSerializer):
    movie_session = MovieSessionListSerializer(read_only=True)

    class Meta:
        model = Ticket
        fields = ("id", "row", "seat", "movie_session")


class TicketWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = Ticket
        fields = ("row", "seat", "movie_session")

    @staticmethod
    def validate_seat(seat, num_seats, error_to_raise):
        if not (1 <= seat <= num_seats):
            raise error_to_raise(
                {
                    "seat": (
                        f"seat must be in range[1, {num_seats}], "
                        f"not {seat}"
                    )
                }
            )

    @staticmethod
    def validate_row(row, num_rows, error_to_raise):
        if not (1 <= row <= num_rows):
            raise error_to_raise(
                {
                    "row": f"row must be in range [1, {num_rows}], not {row}"
                }
            )

    def validate(self, attrs):
        movie_session = attrs.get("movie_session")
        row = attrs.get("row")
        seat = attrs.get("seat")

        self.validate_row(row,
                          movie_session.cinema_hall.rows,
                          serializers.ValidationError
                          )
        self.validate_seat(seat,
                           movie_session.cinema_hall.seats_in_row,
                           serializers.ValidationError
                           )

        if Ticket.objects.filter(
                movie_session=movie_session, row=row, seat=seat
        ).exists():
            raise serializers.ValidationError(
                f"Seat {seat} in row {row} for movie session is already taken."
            )
        return attrs


class OrderSerializer(serializers.ModelSerializer):
    tickets = TicketSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ("id", "tickets", "created_at")


class OrderCreateSerializer(serializers.ModelSerializer):
    tickets = TicketWriteSerializer(many=True)

    class Meta:
        model = Order
        fields = ("tickets",)

    def validate(self, attrs):
        tickets_data = attrs["tickets"]

        # Проверка на дубликаты внутри одного заказа (в запросе)
        seen = set()
        for ticket in tickets_data:
            identifier = (
                ticket["movie_session"]
                .id if hasattr(ticket["movie_session"],
                               "id") else ticket["movie_session"],
                ticket["row"],
                ticket["seat"]
            )
            if identifier in seen:
                raise serializers.ValidationError(
                    f"Duplicate ticket for movie_session={identifier[0]}, "
                    f"row={identifier[1]}, seat={identifier[2]}"
                )
            seen.add(identifier)

        return attrs

    def create(self, validated_data):
        tickets_data = validated_data.pop("tickets")
        user = self.context["request"].user
        order = Order.objects.create(user=user)
        for ticket_data in tickets_data:
            Ticket.objects.create(order=order, **ticket_data)
        return order
