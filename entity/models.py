from itertools import compress

from activatable_model.models import BaseActivatableModel, ActivatableManager, ActivatableQuerySet
from django.contrib.contenttypes import generic
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Count
from django.utils.encoding import python_2_unicode_compatible
from jsonfield import JSONField
from python3_utils import compare_on_attr


class AllEntityKindManager(ActivatableManager):
    """
    Provides additional filtering for entity kinds.
    """
    pass


class ActiveEntityKindManager(AllEntityKindManager):
    """
    Provides additional filtering for entity kinds.
    """
    def get_queryset(self):
        return super(ActiveEntityKindManager, self).get_queryset().filter(is_active=True)


@python_2_unicode_compatible
class EntityKind(BaseActivatableModel):
    """
    A kind for an Entity that is useful for filtering based on different types of entities.
    """
    # The unique identification string for the entity kind
    name = models.CharField(max_length=256, unique=True, db_index=True)

    # A human-readable string for the entity kind
    display_name = models.TextField(blank=True)

    # True if the entity kind is active
    is_active = models.BooleanField(default=True)

    objects = ActiveEntityKindManager()
    all_objects = AllEntityKindManager()

    def __str__(self):
        return self.display_name


class EntityQuerySet(ActivatableQuerySet):
    """
    Provides additional queryset filtering abilities.
    """
    def active(self):
        """
        Returns active entities.
        """
        return self.filter(is_active=True)

    def inactive(self):
        """
        Returns inactive entities.
        """
        return self.filter(is_active=False)

    def is_any_kind(self, *entity_kinds):
        """
        Returns entities that have any of the kinds listed in entity_kinds.
        """
        return self.filter(entity_kind__in=entity_kinds) if entity_kinds else self

    def is_not_any_kind(self, *entity_kinds):
        """
        Returns entities that do not have any of the kinds listed in entity_kinds.
        """
        return self.exclude(entity_kind__in=entity_kinds) if entity_kinds else self

    def is_sub_to_all(self, *super_entities):
        """
        Given a list of super entities, return the entities that have those as a subset of their super entities.
        """
        if super_entities:
            if len(super_entities) == 1:
                # Optimize for the case of just one super entity since this is a much less intensive query
                has_subset = EntityRelationship.objects.filter(
                    super_entity=super_entities[0]).values_list('sub_entity', flat=True)
            else:
                # Get a list of entities that have super entities with all types
                has_subset = EntityRelationship.objects.filter(
                    super_entity__in=super_entities).values('sub_entity').annotate(Count('super_entity')).filter(
                    super_entity__count=len(set(super_entities))).values_list('sub_entity', flat=True)

            return self.filter(id__in=has_subset)
        else:
            return self

    def is_sub_to_any(self, *super_entities):
        """
        Given a list of super entities, return the entities that have super entities that interset with those provided.
        """
        if super_entities:
            return self.filter(id__in=EntityRelationship.objects.filter(
                super_entity__in=super_entities).values_list('sub_entity', flat=True))
        else:
            return self

    def is_sub_to_all_kinds(self, *super_entity_kinds):
        """
        Each returned entity will have superentites whos combined entity_kinds included *super_entity_kinds
        """
        if super_entity_kinds:
            if len(super_entity_kinds) == 1:
                # Optimize for the case of just one
                has_subset = EntityRelationship.objects.filter(
                    super_entity__entity_kind=super_entity_kinds[0]).values_list('sub_entity', flat=True)
            else:
                # Get a list of entities that have super entities with all types
                has_subset = EntityRelationship.objects.filter(
                    super_entity__entity_kind__in=super_entity_kinds).values('sub_entity').annotate(
                    Count('super_entity')).filter(super_entity__count=len(set(super_entity_kinds))).values_list(
                    'sub_entity', flat=True)

            return self.filter(pk__in=has_subset)
        else:
            return self

    def is_sub_to_any_kind(self, *super_entity_kinds):
        """
        Find all entities that have super_entities of any of the specified kinds
        """
        if super_entity_kinds:
            # get the pks of the desired subs from the relationships table
            if len(super_entity_kinds) == 1:
                entity_pks = EntityRelationship.objects.filter(
                    super_entity__entity_kind=super_entity_kinds[0]
                ).select_related('entity_kind', 'sub_entity').values_list('sub_entity', flat=True)
            else:
                entity_pks = EntityRelationship.objects.filter(
                    super_entity__entity_kind__in=super_entity_kinds
                ).select_related('entity_kind', 'sub_entity').values_list('sub_entity', flat=True)
            # return a queryset limited to only those pks
            return self.filter(pk__in=entity_pks)
        else:
            return self

    def cache_relationships(self, cache_super=True, cache_sub=True):
        """
        Caches the super and sub relationships by doing a prefetch_related.
        """
        relationships_to_cache = compress(
            ['super_relationships__super_entity', 'sub_relationships__sub_entity'], [cache_super, cache_sub])
        return self.prefetch_related(*relationships_to_cache)


class AllEntityManager(ActivatableManager):
    """
    Provides additional entity-wide filtering abilities over all of the entity objects.
    """
    def get_queryset(self):
        return EntityQuerySet(self.model)

    def get_for_obj(self, entity_model_obj):
        """
        Given a saved entity model object, return the associated entity.
        """
        return self.get(entity_type=ContentType.objects.get_for_model(
            entity_model_obj, for_concrete_model=False), entity_id=entity_model_obj.id)

    def delete_for_obj(self, entity_model_obj):
        """
        Delete the entities associated with a model object.
        """
        return self.filter(
            entity_type=ContentType.objects.get_for_model(
                entity_model_obj, for_concrete_model=False), entity_id=entity_model_obj.id).delete(
            force=True)

    def active(self):
        """
        Returns active entities.
        """
        return self.get_queryset().active()

    def inactive(self):
        """
        Returns inactive entities.
        """
        return self.get_queryset().inactive()

    def is_any_kind(self, *entity_kinds):
        """
        Returns entities that have any of the kinds listed in entity_kinds.
        """
        return self.get_queryset().is_any_kind(*entity_kinds)

    def is_not_any_kind(self, *entity_kinds):
        """
        Returns entities that do not have any of the kinds listed in entity_kinds.
        """
        return self.get_queryset().is_not_any_kind(*entity_kinds)

    def is_sub_to_all_kinds(self, *super_entity_kinds):
        """
        Each returned entity will have superentites whos combined entity_kinds included *super_entity_kinds
        """
        return self.get_queryset().is_sub_to_all_kinds(*super_entity_kinds)

    def is_sub_to_any_kind(self, *super_entity_kinds):
        """
        Find all entities that have super_entities of any of the specified kinds
        """
        return self.get_queryset().is_sub_to_any_kind(*super_entity_kinds)

    def is_sub_to_all(self, *super_entities):
        """
        Given a list of super entities, return the entities that have those super entities as a subset of theirs.
        """
        return self.get_queryset().is_sub_to_all(*super_entities)

    def is_sub_to_any(self, *super_entities):
        """
        Given a list of super entities, return the entities whose super entities intersect with the provided super
        entities.
        """
        return self.get_queryset().is_sub_to_any(*super_entities)

    def cache_relationships(self, cache_super=True, cache_sub=True):
        """
        Caches the super and sub relationships by doing a prefetch_related.
        """
        return self.get_queryset().cache_relationships(cache_super=cache_super, cache_sub=cache_sub)


class ActiveEntityManager(AllEntityManager):
    """
    The default 'objects' on the Entity model. This manager restricts all Entity queries to happen over active
    entities.
    """
    def get_queryset(self):
        return EntityQuerySet(self.model).active()


@compare_on_attr()
@python_2_unicode_compatible
class Entity(BaseActivatableModel):
    """
    Describes an entity and its relevant metadata. Also defines if the entity is active. Filtering functions
    are provided that mirror the filtering functions in the Entity model manager.
    """
    # A human-readable name for the entity
    display_name = models.TextField(blank=True, db_index=True)

    # The generic entity
    entity_id = models.IntegerField()
    entity_type = models.ForeignKey(ContentType, on_delete=models.PROTECT)
    entity = generic.GenericForeignKey('entity_type', 'entity_id')

    # The entity kind
    entity_kind = models.ForeignKey(EntityKind, on_delete=models.PROTECT)

    # Metadata about the entity, stored as JSON
    entity_meta = JSONField(null=True)

    # True if this entity is active
    is_active = models.BooleanField(default=True, db_index=True)

    objects = ActiveEntityManager()
    all_objects = AllEntityManager()

    class Meta:
        unique_together = ('entity_id', 'entity_type', 'entity_kind')

    def get_sub_entities(self):
        """
        Returns all of the sub entities of this entity. The returned entities may be filtered by chaining any
        of the functions in EntityFilter.
        """
        return [r.sub_entity for r in self.sub_relationships.all()]

    def get_super_entities(self):
        """
        Returns all of the super entities of this entity. The returned super entities may be filtered by
        chaining methods from EntityFilter.
        """
        return [r.super_entity for r in self.super_relationships.all()]

    def __str__(self):
        """Return the display_name field
        """
        return self.display_name


class EntityRelationship(models.Model):
    """
    Defines a relationship between two entities, telling which
    entity is a superior (or sub) to another entity. Similary, this
    model allows us to define if the relationship is active.
    """
    # The sub entity. The related name is called super_relationships since
    # querying this reverse relationship returns all of the relationships
    # super to an entity
    sub_entity = models.ForeignKey(Entity, related_name='super_relationships')

    # The super entity. The related name is called sub_relationships since
    # querying this reverse relationships returns all of the relationships
    # sub to an entity
    super_entity = models.ForeignKey(Entity, related_name='sub_relationships')
