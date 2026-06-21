from rest_framework import serializers
from django.db import transaction

from .models import (
    User,
    UserProfile,
    UserActivityAccess,
    Person,
    Department,
    Activity,
    Member,
    Drug,
    DrugStock,
    DrugDonation,
    DonationItem,
    DrugDistribution,
    DistributionItem,
)


# ─────────────────────────────────────────────
# AUTH / USER SERIALIZERS  (new)
# ─────────────────────────────────────────────

class UserActivityAccessSerializer(serializers.ModelSerializer):
    activity_name   = serializers.CharField(source='activity.name',            read_only=True)
    department_name = serializers.CharField(source='activity.department.name',  read_only=True)

    class Meta:
        model  = UserActivityAccess
        fields = ['id', 'activity', 'activity_name', 'department_name', 'access_level', 'granted_at']
        read_only_fields = ['granted_at']


class UserProfileSerializer(serializers.ModelSerializer):
    """Lightweight profile — just the linked person id and name."""
    person_name = serializers.SerializerMethodField()

    class Meta:
        model  = UserProfile
        fields = ['person', 'person_name']

    def get_person_name(self, obj):
        if obj.person:
            return f"{obj.person.first_name} {obj.person.last_name}"
        return None


class UserSerializer(serializers.ModelSerializer):
    """
    Read-only user info returned after login or from /api/auth/me/.
    Shows the linked person and all activity accesses.
    """
    profile          = UserProfileSerializer(read_only=True)
    activity_accesses = UserActivityAccessSerializer(many=True, read_only=True)

    class Meta:
        model  = User
        fields = [
            'id', 'username', 'first_name', 'last_name',
            'email', 'is_active', 'is_superuser',
            'profile', 'activity_accesses',
        ]


# ─────────────────────────────────────────────
# PERSON
# ─────────────────────────────────────────────

class PersonSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()

    class Meta:
        model  = Person
        fields = "__all__"


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Department
        fields = "__all__"


class ActivitySerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True)

    class Meta:
        model  = Activity
        fields = ['id', 'name', 'description', 'department', 'department_name']


class MemberSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Member
        fields = "__all__"


# ─────────────────────────────────────────────
# DRUG
# ─────────────────────────────────────────────

class DrugSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Drug
        fields = "__all__"


# ─────────────────────────────────────────────
# STOCK
# ─────────────────────────────────────────────

class DrugStockSerializer(serializers.ModelSerializer):
    drug_name   = serializers.CharField(source='drug.dci_name', read_only=True)
    drug_dosage = serializers.CharField(source='drug.dosage',   read_only=True)
    drug_form   = serializers.CharField(source='drug.form',     read_only=True)

    class Meta:
        model  = DrugStock
        fields = [
            'id', 'drug', 'drug_name', 'drug_dosage', 'drug_form',
            'expiration_date', 'quantity_available', 'created_at',
        ]


# ─────────────────────────────────────────────
# DONATIONS
# ─────────────────────────────────────────────

class DonationItemSerializer(serializers.ModelSerializer):
    drug_name = serializers.CharField(source='drug.dci_name', read_only=True)

    class Meta:
        model  = DonationItem
        fields = ['id', 'drug', 'drug_name', 'quantity', 'expiration_date']


class DrugDonationSerializer(serializers.ModelSerializer):
    items = DonationItemSerializer(many=True)
    cancelled_by_username = serializers.CharField(source='cancelled_by.username', read_only=True)
    class Meta:
        model  = DrugDonation
        fields = "__all__"
        read_only_fields = ['is_cancelled', 'cancelled_at', 'cancelled_by']
    # in normall case we would use nested writable serializers for create/update, but since we have some custom logic to handle stock validation and immutability of items after creation, we override create() and update() methods instead.   
    # The create() method creates the donation and its items in a single transaction, ensuring data integrity.
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        with transaction.atomic():
            donation = DrugDonation.objects.create(**validated_data)
            for item_data in items_data:
                DonationItem.objects.create(donation=donation, **item_data)
        return donation
    
    #  The update() method allows changing only the header fields of the donation, while preventing any modifications to the items after creation, thus maintaining an audit trail. 
    def update(self, instance, validated_data):
        if instance.is_cancelled:
            raise serializers.ValidationError("A cancelled donation cannot be modified.")
        items_data = validated_data.pop('items', None)
        if items_data is not None:
            raise serializers.ValidationError(
                {"items": "Donation items cannot be modified after creation."}
            )
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


# ─────────────────────────────────────────────
# DISTRIBUTIONS
# ─────────────────────────────────────────────

class DistributionItemSerializer(serializers.ModelSerializer):
    # ── Read-only display fields ──────────────────────────────────────────
    drug_name       = serializers.CharField(source='stock.drug.dci_name',  read_only=True)
    expiration_date = serializers.DateField(source='stock.expiration_date', read_only=True)

    # ── Write-only convenience field ──────────────────────────────────────
    # The frontend sends { drug: <id>, quantity: N }.
    # We resolve it to the earliest non-expired DrugStock automatically.
    # If you already know the exact stock batch, send { stock: <id>, quantity: N } instead.
    drug = serializers.PrimaryKeyRelatedField(
        queryset=Drug.objects.all(),
        write_only=True,
        required=False,
        help_text="Send drug id and we'll pick the earliest valid stock batch automatically."
    )

    class Meta:
        model  = DistributionItem
        fields = ['id', 'stock', 'drug', 'drug_name', 'expiration_date', 'quantity']
        extra_kwargs = {
            # stock is optional on input — can be resolved from drug
            'stock': {'required': False},
        }

    def validate(self, data):
        drug  = data.pop('drug', None)
        stock = data.get('stock', None)

        if stock is None and drug is None:
            raise serializers.ValidationError(
                "Provide either 'stock' (exact batch id) or 'drug' (we pick the earliest batch)."
            )

        if stock is None:
            # Auto-pick the earliest non-expired batch with enough stock
            from django.utils import timezone
            today = timezone.now().date()
            quantity = data.get('quantity', 0)
            stock = (
                DrugStock.objects
                .filter(
                    drug=drug,
                    quantity_available__gte=quantity,
                    expiration_date__gt=today,
                )
                .order_by('expiration_date')   # FEFO — First Expired, First Out
                .first()
            )
            if stock is None:
                raise serializers.ValidationError(
                    {
                        "drug": (
                            f"No available stock for '{drug.dci_name} {drug.dosage}' "
                            f"with at least {quantity} units that hasn't expired."
                        )
                    }
                )
            data['stock'] = stock

        return data


class DrugDistributionSerializer(serializers.ModelSerializer):
    items            = DistributionItemSerializer(many=True)
    beneficiary_name = serializers.SerializerMethodField()

    class Meta:
        model  = DrugDistribution
        fields = "__all__"

    def get_beneficiary_name(self, obj):
        return f"{obj.beneficiary.first_name} {obj.beneficiary.last_name}"

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        with transaction.atomic():
            distribution = DrugDistribution.objects.create(**validated_data)
            for item_data in items_data:
                DistributionItem.objects.create(distribution=distribution, **item_data)
        # Stock is NOT deducted here — only when validate() is called
        return distribution

    def update(self, instance, validated_data):
        """
        Allow editing header fields and replacing items — but ONLY if the
        distribution has not been validated yet (stock already deducted).
        """
        if instance.is_validated:
            raise serializers.ValidationError(
                "A validated distribution cannot be modified."
            )

        items_data = validated_data.pop('items', None)

        # Update header fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Replace items if provided
        if items_data is not None:
            with transaction.atomic():
                instance.items.all().delete()
                for item_data in items_data:
                    DistributionItem.objects.create(distribution=instance, **item_data)

        return instance


class MeUpdateSerializer(serializers.ModelSerializer):
    """
    Allows a regular user to update ONLY their own password.
    Username is explicitly read-only — only admin can change it.
    """
    password     = serializers.CharField(write_only=True, required=True, min_length=6)
    old_password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model  = User
        fields = ['old_password', 'password']

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('كلمة المرور الحالية غير صحيحة.')
        return value

    def update(self, instance, validated_data):
        validated_data.pop('old_password')
        instance.set_password(validated_data['password'])
        instance.save()
        return instance
    
# ─────────────────────────────────────────────
# USER MANAGEMENT SERIALIZERS (admin only)
# ─────────────────────────────────────────────

class UserCreateSerializer(serializers.ModelSerializer):
    """Used by superuser to create a new user with a password."""
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model  = User
        fields = ['id', 'username', 'password', 'first_name', 'last_name', 'email', 'is_active', 'is_staff']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Used by superuser to update a user. Password is optional."""
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model  = User
        fields = ['id', 'username', 'password', 'first_name', 'last_name', 'email', 'is_active', 'is_staff']

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance