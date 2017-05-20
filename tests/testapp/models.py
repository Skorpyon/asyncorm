from asyncorm.fields import (
    CharField, DateField, EmailField, ForeignKey, IntegerField, JsonField,
    ManyToMany, PkField,
)

from asyncorm.model import Model

BOOK_CHOICES = (
    ('hard cover', 'hard cover book'),
    ('paperback', 'paperback book')
)


SIZE_CHOICES = (
    ('XS', 'XS'),
    ('S', 'S'),
    ('M', 'M'),
    ('L', 'L'),
    ('XL', 'XL'),
)
POWER_CHOICES = {
    'neo': 'feo',
    'pow': 'dow',
    'saw': 'mao',
}


def weight():
    return 85


class Publisher(Model):
    name = CharField(max_length=50)
    json = JsonField(max_length=50, null=True)


class Author(Model):
    na = PkField(field_name='uid')
    name = CharField(max_length=50, unique=True)
    email = EmailField(max_length=100, null=True)
    age = IntegerField()
    publisher = ManyToMany(foreign_key='Publisher')


class Book(Model):
    name = CharField(max_length=50)
    content = CharField(max_length=255, choices=BOOK_CHOICES)
    date_created = DateField(auto_now=True)
    author = ForeignKey(foreign_key='Author', null=True)

    def its_a_2(self):
        return 2

    class Meta():
        table_name = 'library'
        ordering = ['-id', ]
        unique_together = ['name', 'content']


class Reader(Model):
    name = CharField(max_length=15, default='pepito')
    size = CharField(choices=SIZE_CHOICES, max_length=2)
    power = CharField(choices=POWER_CHOICES, max_length=2, null=True)
    weight = IntegerField(default=weight)
