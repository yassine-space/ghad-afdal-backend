from rest_framework import serializers
from django.db import transaction

from .models import (
    DonationHistory,
    Donor,
    Patient,
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
    Machine,
    MachineAssignment,
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
    is_online         = serializers.ReadOnlyField()
    last_activity     = serializers.DateTimeField(read_only=True)

    class Meta:
        model  = User
        fields = [
            'id', 'username', 'first_name', 'last_name',
            'email', 'is_active', 'is_superuser',
            'profile', 'activity_accesses', 'is_online', 'last_activity'
        ]


# ─────────────────────────────────────────────
# PERSON
# ─────────────────────────────────────────────

class PersonSerializer(serializers.ModelSerializer):
    age = serializers.ReadOnlyField()

    class Meta:
        model  = Person
        fields = "__all__"


# ─────────────────────────────────────────────
# DEPARTMENT & ACTIVITY
# ─────────────────────────────────────────────

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
    items                  = DonationItemSerializer(many=True)
    can_be_cancelled       = serializers.ReadOnlyField()
    cancelled_by_username   = serializers.CharField(source='cancelled_by.username', read_only=True, default=None)

    class Meta:
        model  = DrugDonation
        fields = "__all__" 

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        with transaction.atomic():
            donation = DrugDonation.objects.create(**validated_data)
            for item_data in items_data:
                DonationItem.objects.create(donation=donation, **item_data)
        return donation

    def update(self, instance, validated_data):
        """
        Update header fields only (donor, type, date, price, remarks).
        Items are intentionally immutable after creation — they form an
        audit trail and each one triggers a stock signal.
        To change items, delete the donation and create a new one.
        """
        items_data = validated_data.pop('items', None)
        if items_data is not None:
            raise serializers.ValidationError(
                {"items": "Donation items cannot be modified after creation. "
                          "Delete this donation and create a new one."}
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

    class Meta:
        model  = DistributionItem
        fields = ['id', 'stock', 'drug_name', 'expiration_date', 'quantity']


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
    



# blood donation management 
class DonorSerializer(serializers.ModelSerializer):
    person_name = serializers.SerializerMethodField()
    person_nin  = serializers.CharField(source='person.nin', read_only=True)
    can_donate = serializers.SerializerMethodField()

    class Meta:
        model  = Donor
        fields = ['id', 'person', 'person_name', 'person_nin', 'blood_type',
                  'date_last_donation', 'is_approved', 'description', 'can_donate']

    def get_person_name(self, obj):
        return f"{obj.person.first_name} {obj.person.last_name}"

    def get_can_donate(self, obj):
        return obj.can_donate

class PatientSerializer(serializers.ModelSerializer):
    person_name = serializers.SerializerMethodField()
    person_nin  = serializers.CharField(source='person.nin', read_only=True)

    class Meta:
        model  = Patient
        fields = ['id', 'person', 'person_name', 'person_nin', 'blood_type',
                  'hospital_name', 'description', 'is_active']

    def get_person_name(self, obj):
        return f"{obj.person.first_name} {obj.person.last_name}"



class PatientWithCompatibleDonorsSerializer(serializers.Serializer):
    patient = PatientSerializer()
    donors  = DonorSerializer(many=True)


class DonationHistorySerializer(serializers.ModelSerializer):
    donor_name         = serializers.CharField(source='donor.person.first_name', read_only=True)
    donor_last_name    = serializers.CharField(source='donor.person.last_name', read_only=True)
    patient_name       = serializers.CharField(source='patient.person.first_name', read_only=True)
    patient_last_name  = serializers.CharField(source='patient.person.last_name', read_only=True)
    blood_type         = serializers.CharField(source='patient.blood_type', read_only=True)
    hospital           = serializers.CharField(source='patient.hospital_name', read_only=True)

    class Meta:
        model  = DonationHistory
        fields = '__all__'



class MachineSerializer(serializers.ModelSerializer):
    photo_url           = serializers.SerializerMethodField()
    class Meta:
        model  = Machine
        fields = [
            'id', 'bar_code', 'name', 'description',
            'status', 'photo', 'photo_url','acquisition_date'
        ]
        read_only_fields = ['bar_code']   # auto-generated

    def get_photo_url(self, obj):
        if not obj.photo:
            return None
        url = obj.photo.url
        if url.startswith('http://') or url.startswith('https://'):
            # Already an absolute URL (R2/S3 storage) — use as-is
            return url
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(url)
        return url


class MachineAssignmentSerializer(serializers.ModelSerializer):
    person_name  = serializers.SerializerMethodField()
    machine_name = serializers.CharField(source='machine.name',     read_only=True)
    bar_code     = serializers.CharField(source='machine.bar_code', read_only=True)
    is_returned  = serializers.SerializerMethodField()
    person_phone = serializers.CharField(source='assigned_to.phone', read_only=True)
    class Meta:
        model  = MachineAssignment
        fields = [
            'id', 'machine', 'machine_name', 'bar_code',
            'assigned_to', 'person_name', 'person_phone',
            'assigned_at', 'returned_at', 'is_returned',
            'description',
        ]
        read_only_fields = ['returned_at']

    def get_person_name(self, obj):
        return f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}"

    def get_is_returned(self, obj):
        return obj.returned_at is not None

    def validate(self, data):
        machine = data.get('machine')
        # On create only — block assigning an already-assigned machine
        if self.instance is None and machine and machine.status == 'assigned':
            raise serializers.ValidationError(
                {'machine': f'الجهاز "{machine.name}" مُسند حالياً. يجب إرجاعه أولاً.'}
            )
        return data
    


from .models import FinancialCategory, Donation, ExpenseTransaction,  FinancialAuditLog, log_finance_action


class FinancialCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = FinancialCategory
        fields = ['id', 'name', 'is_active']

class DonationSerializer(serializers.ModelSerializer):
    category_name   = serializers.CharField(source='category.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)

    class Meta:
        model  = Donation
        fields = [
            'id', 'donor_name', 'amount', 'payment_method', 'category', 'category_name',
            'date', 'notes', 'created_by', 'created_by_name', 'created_at',
        ]
        read_only_fields = ['created_by', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user if request else None
        instance = super().create(validated_data)
        log_finance_action(request.user if request else None, 'create', 'Donation', instance.id,
                            f"{instance.donor_name} - {instance.amount} DZD")
        return instance

    def update(self, instance, validated_data):
        request = self.context.get('request')
        instance = super().update(instance, validated_data)
        log_finance_action(request.user if request else None, 'update', 'Donation', instance.id)
        return instance


class ExpenseTransactionSerializer(serializers.ModelSerializer):
    category_name   = serializers.CharField(source='category.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True, default=None)

    class Meta:
        model  = ExpenseTransaction
        fields = [
            'id', 'amount', 'category', 'category_name', 'description', 'date',
            'created_by', 'created_by_name', 'related_donation', 'created_at',
        ]
        read_only_fields = ['created_by', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        validated_data['created_by'] = request.user if request else None
        instance = super().create(validated_data)
        log_finance_action(request.user if request else None, 'create', 'ExpenseTransaction', instance.id,
                            f"{instance.amount} DZD - {instance.description}")
        return instance

    def update(self, instance, validated_data):
        request = self.context.get('request')
        instance = super().update(instance, validated_data)
        log_finance_action(request.user if request else None, 'update', 'ExpenseTransaction', instance.id)
        return instance
    
class FinancialAuditLogSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True, default=None)

    class Meta:
        model  = FinancialAuditLog
        fields = ['id', 'username', 'action', 'model_name', 'object_id', 'details', 'timestamp']