import uuid
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser
from datetime import date, timedelta
from django.utils import timezone
import unicodedata
class User(AbstractUser):
    last_activity = models.DateTimeField(null=True, blank=True)
    """
    Custom User model replacing Django's default.
    We extend AbstractUser so we keep all default fields
    (username, password, is_active, is_staff, is_superuser…)
    and add nothing extra here — the extra info lives in UserProfile.
    """

    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.username
    
    @property
    def is_online(self):
        if not self.last_activity:
            return False
        return (timezone.now() - self.last_activity) <= timedelta(minutes=5)

class Person(models.Model):
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female')]

    first_name    = models.CharField(max_length=100)
    last_name     = models.CharField(max_length=100)
    nin           = models.CharField(max_length=20, null=True, blank=True)
    phone         = models.CharField(max_length=14, blank=True, null=True)
    address       = models.TextField()
    date_of_birth = models.DateField()
    gender        = models.CharField(max_length=1, choices=GENDER_CHOICES)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'persons'
        ordering = ['last_name', 'first_name']

    def __str__(self):
      return f"{self.first_name} {self.last_name} ({self.nin or 'No NIN'})"

    @property
    def age(self):
        today = date.today()
        return today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )


class UserProfile(models.Model):
    """
    Connects a system User (login account) to a real Person in the database.
    Every non-superuser should have a profile.
    The superuser/admin does NOT need a profile — they bypass everything.

    This is created automatically when a User is created (see signal below).
    The admin then fills in the 'person' field to link them.
    """
    user   = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    person = models.OneToOneField(
        Person,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='user_profile',
        help_text="The real person this login account belongs to."
    )

    class Meta:
        db_table = 'user_profiles'

    def __str__(self):
        if self.person:
            return f"Profile of {self.user.username} → {self.person}"
        return f"Profile of {self.user.username} (no person linked)"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Auto-create a UserProfile every time a new User is saved."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


class Department(models.Model):
  
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Activity(models.Model):
    """
    A specific activity run by a department.
    One department can have many activities.
    This is the PERMISSION UNIT of the system —
    users are granted access to specific activities
    """
    department  = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='activities',
        blank=True,
        null=True
    )
    name        = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} ({self.department})"


class Member(models.Model):
    """
    Connects a Person to a Department with a role and join date.
    A person can be a member of multiple departments.
    """
    person    = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='members'
    )
    role      = models.CharField(max_length=100)
    join_date = models.DateField()

    def __str__(self):
        return f"{self.person} — {self.role} @ {self.department}"


class UserActivityAccess(models.Model):
    """
    The core permission table.
    Answers the question: "What can this user do inside this activity?"

    Access levels:
      viewer  → can only read/list data
      editor  → can add and edit data
      manager → can add, edit, delete, and validate

    One user can have multiple rows — one per activity assigned.
    The admin manages this entirely from the admin panel.

    Example rows:
      Ahmed  | Pharmacy (Medical Dept) | editor
      Ahmed  | Stock    (Medical Dept) | viewer
      Sara   | Social Aid (Social Dept)| manager
    """
    ACCESS_LEVELS = [
        ('viewer',  'Viewer  — read only'),
        ('editor',  'Editor  — add and edit'),
        ('manager', 'Manager — full control'),
    ]

    user         = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activity_accesses'
    )
    activity     = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name='user_accesses'
    )
    access_level = models.CharField(
        max_length=10,
        choices=ACCESS_LEVELS,
        default='viewer'
    )
    granted_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'user_activity_access'
        # One row per user+activity combination — no duplicates
        unique_together = [['user', 'activity']]
        verbose_name    = 'User Activity Access'
        verbose_name_plural = 'User Activity Accesses'

    def __str__(self):
        return (
            f"{self.user.username} → "
            f"{self.activity.name} ({self.activity.department}) "
            f"[{self.get_access_level_display()}]"
        )


# ─────────────────────────────────────────────
# STEP 7 — PERMISSION HELPER FUNCTIONS
# Import and use these in every view.
# ─────────────────────────────────────────────

def get_user_activities(user):
    """
    Returns all UserActivityAccess rows for a given user.
    Use this to know what activities a user can see at all.

    Usage in a view:
        accesses = get_user_activities(request.user)
    """
    return UserActivityAccess.objects.filter(user=user).select_related(
        'activity', 'activity__department'
    )


def has_activity_access(user, activity_name, department_name, level='viewer'):
    """
    Check if a user has at least the given access level
    for a specific activity inside a specific department.

    Levels are hierarchical:
        manager >= editor >= viewer

    Usage in a view:
        if not has_activity_access(request.user, 'Pharmacy', 'Medical', 'editor'):
            return redirect('not_authorized')

    Returns True for superusers automatically — they bypass all checks.
    """
    if user.is_superuser:
        return True

    LEVEL_RANK = {'viewer': 1, 'editor': 2, 'manager': 3}
    required_rank = LEVEL_RANK.get(level, 1)

    try:
        access = UserActivityAccess.objects.get(
            user=user,
            activity__name__iexact=activity_name,
            activity__department__name__iexact=department_name
        )
        return LEVEL_RANK.get(access.access_level, 0) >= required_rank
    except UserActivityAccess.DoesNotExist:
        return False



class Drug(models.Model):
    """
    The drug catalogue. Defines what a drug IS — not how much we have.
    Quantities and batches live in DrugStock.
    """
    FORM_CHOICES = [
        ('tablet',    'Tablet'),
        ('syrup',     'Syrup'),
        ('injection', 'Injection'),
        ('cream',     'Cream'),
        ('other',     'Other'),
    ]

    code     = models.CharField(max_length=25, unique=True)
    dci_name = models.CharField(max_length=255)
    form     = models.CharField(max_length=20, choices=FORM_CHOICES)
    dosage   = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.dci_name} {self.dosage}"


class DrugDonation(models.Model):
    DONATION_TYPES = [
        ('donation', 'Donation'),
        ('invoice',  'Invoice'),
        ('supply',   'Supply'),
        ('other',    'Other'),
    ]

    CANCELLATION_WINDOW_DAYS = 5
    donor          = models.CharField(max_length=100)
    donation_type  = models.CharField(max_length=20, choices=DONATION_TYPES)
    invoice_number = models.CharField(max_length=100, blank=True, null=True)
    donation_date  = models.DateField()
    total_price    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remarks        = models.TextField(blank=True)
    is_cancelled     = models.BooleanField(default=False)
    cancelled_at     = models.DateTimeField(null=True, blank=True)
    cancelled_by     = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,)
    cancellation_reason = models.TextField(blank=True)
    class Meta:
        ordering = ['-donation_date']

    def __str__(self):
        return f"{self.get_donation_type_display()} from {self.donor} ({self.donation_date})"
    @property
    def can_be_cancelled(self):
        """
        True only if the donation hasn't been cancelled yet AND it was
        logged within CANCELLATION_WINDOW_DAYS of its donation_date.
        """
        if self.is_cancelled:
            return False
        return (timezone.now().date() - self.donation_date) <= timedelta(days=self.CANCELLATION_WINDOW_DAYS)
    
    def cancel(self, user, reason=''):
        from django.db import transaction
    
        if self.is_cancelled:
            raise ValidationError("This donation has already been cancelled.")
    
        if not self.can_be_cancelled:
            raise ValidationError(
                f"This donation can no longer be cancelled — cancellation is only "
                f"allowed within {self.CANCELLATION_WINDOW_DAYS} days of its donation "
                f"date ({self.donation_date})."
            )
    
        with transaction.atomic():
            for item in self.items.select_related('drug'):
                try:
                    stock = DrugStock.objects.get(
                        drug=item.drug,
                        expiration_date=item.expiration_date,
                    )
                except DrugStock.DoesNotExist:
                    raise ValidationError(
                        f"Stock batch for {item.drug} (exp {item.expiration_date}) no longer exists."
                    )
                if stock.quantity_available < item.quantity:
                    raise ValidationError(
                        f"Cannot cancel: only {stock.quantity_available} units remain of "
                        f"{item.drug} (exp {item.expiration_date}), but {item.quantity} were "
                        f"donated — some have already been distributed."
                    )
                stock.quantity_available -= item.quantity
                stock.save()
    
            self.is_cancelled = True
            self.cancelled_at = timezone.now()
            self.cancelled_by = user
            self.cancellation_reason = reason
            self.save()

class DonationItem(models.Model):
    """
    One line inside a donation.
    NEVER modified after creation — permanent audit trail.
    A post_save signal auto-creates/updates DrugStock.
    """
    donation        = models.ForeignKey(DrugDonation, on_delete=models.CASCADE, related_name='items')
    drug            = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='donation_items')
    quantity        = models.PositiveIntegerField()
    expiration_date = models.DateField()

    def __str__(self):
        return f"{self.drug} x{self.quantity} (exp: {self.expiration_date})"


# ─────────────────────────────────────────────
# STOCK
# ─────────────────────────────────────────────

class DrugStock(models.Model):
    drug               = models.ForeignKey(Drug, on_delete=models.PROTECT, related_name='stocks')
    expiration_date    = models.DateField()
    quantity_available = models.PositiveIntegerField(default=0)
    created_at         = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering       = ['expiration_date']
        unique_together = [['drug', 'expiration_date']]

    def __str__(self):
        return f"{self.drug} — ({self.quantity_available} left, exp: {self.expiration_date})"

    def deduct(self, quantity):
        if quantity > self.quantity_available:
            raise ValidationError(
                f"Cannot deduct {quantity} from stock of {self.drug} "
                f"expiring {self.expiration_date}. "
                f"Only {self.quantity_available} available."
            )
        self.quantity_available -= quantity
        self.save()


@receiver(post_save, sender=DonationItem)
def create_stock_from_donation_item(sender, instance, created, **kwargs):
    if created:
        stock, was_created = DrugStock.objects.get_or_create(
            drug=instance.drug,
            expiration_date=instance.expiration_date,
            defaults={'quantity_available': 0}
        )
        stock.quantity_available += instance.quantity
        stock.save()


# ─────────────────────────────────────────────
# DISTRIBUTIONS
# ─────────────────────────────────────────────

class DrugDistribution(models.Model):
    beneficiary         = models.ForeignKey(Person, on_delete=models.PROTECT, related_name='drug_distributions')
    distribution_date   = models.DateField()
    prescription_number = models.CharField(max_length=100)
    doctor_name         = models.CharField(max_length=255)
    remarks             = models.TextField(blank=True)
    is_validated        = models.BooleanField(default=False)

    class Meta:
        ordering = ['-distribution_date']

    def __str__(self):
        return f"Distribution #{self.id} → {self.beneficiary} ({self.distribution_date})"

    def validate(self):
        from django.db import transaction
        if self.is_validated:
            raise ValidationError("This distribution has already been validated.")
        with transaction.atomic():
            for item in self.items.select_related('stock'):
                item.stock.deduct(item.quantity)
            self.is_validated = True
            self.save()


class DistributionItem(models.Model):
    distribution = models.ForeignKey(DrugDistribution, on_delete=models.CASCADE, related_name='items')
    stock        = models.ForeignKey(DrugStock, on_delete=models.PROTECT, related_name='distribution_items')
    quantity     = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.stock.drug} x{self.quantity}"
    
# _____________________________________________
# blood donation management models
#__________________________________________

class Donor(models.Model):
    BLOOD_TYPES = [
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-'),
    ]
    person             = models.OneToOneField(Person, on_delete=models.CASCADE, related_name='donor_profile')
    blood_type         = models.CharField(max_length=3, choices=BLOOD_TYPES, blank=True, null=True)
    date_last_donation = models.DateField(blank=True, null=True)
    is_approved        = models.BooleanField(default=False)
    description        = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'donor'

    def __str__(self):
        return f"{self.person.first_name} {self.person.last_name}"
    @property
    def can_donate(self):
        """Check if the donor can donate (90 days between donations)."""
        if not self.date_last_donation:
            return True
        three_months_ago = date.today() - timedelta(days=90)
        return self.date_last_donation <= three_months_ago


class Patient(models.Model):
    BLOOD_TYPES = Donor.BLOOD_TYPES  # reuse instead of repeating the same tuple list

    person        = models.OneToOneField(Person, on_delete=models.CASCADE, related_name='patient_profile')
    blood_type    = models.CharField(max_length=3, choices=BLOOD_TYPES, blank=True, null=True)
    hospital_name = models.CharField(max_length=255, blank=True, null=True)
    description   = models.TextField(blank=True, null=True)
    is_active     = models.BooleanField(default=True)

    class Meta:
        db_table = 'patient'

    def __str__(self):
        return f"{self.person.first_name} {self.person.last_name}"


class DonationHistory(models.Model):

    patient       = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='donations_received')
    donor         = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name='donations_given')
    donation_date = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'donation_history'
        ordering = ['-donation_date']

    def __str__(self):
        return f"{self.donor.person.first_name} تبرع لـ {self.patient.person.first_name} في {self.donation_date}"
    

# ─────────────────────────────────────────────
# MEDICAL MACHINES
# ─────────────────────────────────────────────

class Machine(models.Model):

    STATUS_CHOICES = [
        ('available', 'Available'),
        ('destroyed', 'Destroyed'),
        ('maintenance', 'Under Maintenance'),
        ('assigned', 'Assigned'),
    ]

    bar_code = models.CharField(max_length=50, unique=True, blank=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    photo = models.ImageField(upload_to='machines/', blank=True, null=True)
    acquisition_date = models.DateField(null=True, blank=True)
    class Meta:
        db_table = 'medical_machine'
        ordering = ['id']
    def save(self, *args, **kwargs):
        if self.pk is None:
            super().save(*args, **kwargs)
    
        if not self.bar_code:
            words = self.name.strip().split()
            if len(words) == 1:
                prefix = words[0][:3].upper()
            else:
                prefix = "".join(word[0].upper() for word in words)
    
            prefix = unicodedata.normalize('NFKD', prefix).encode('ascii', 'ignore').decode('ascii')
            prefix = ''.join(ch for ch in prefix if ch.isalnum())
    
            if not prefix:
                prefix = 'MC'  # fallback when name is fully non-Latin (e.g. Arabic)
    
            self.bar_code = f"M-{prefix}{self.id}"
            super().save(update_fields=["bar_code"])
        else:
            super().save(*args, **kwargs)
    def __str__(self):

        return f"{self.name} ({self.bar_code}) - {self.status}"

class MachineAssignment(models.Model):
    machine     = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='assignments')
    assigned_to = models.ForeignKey(Person,  on_delete=models.CASCADE, related_name='machine_assignments')
    assigned_at = models.DateTimeField(default=timezone.now)
    returned_at = models.DateTimeField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'machine_assignment'
        ordering = ['-assigned_at']

    def __str__(self):
        return (
            f"{self.machine.name} → "
            f"{self.assigned_to.first_name} {self.assigned_to.last_name} "
            f"({self.assigned_at:%Y-%m-%d})"
        )

    def return_machine(self, returned_at=None, return_description=''):
        """Mark assignment as returned with optional return date and note."""
        from django.utils import timezone
        if self.returned_at:
            raise ValidationError("This assignment has already been returned.")

        self.returned_at = returned_at or timezone.now()

        note = (return_description or '').strip()
        if note:
            existing = (self.description or '').strip()
            return_note = f"{note}"
            self.description = f"{existing}\n{return_note}" if existing else return_note

        self.save()
        # Only mark available if no other active assignment exists
        active = MachineAssignment.objects.filter(
            machine=self.machine, returned_at__isnull=True
        ).exclude(pk=self.pk).exists()
        if not active:
            self.machine.status = 'available'
            self.machine.save()


@receiver(post_save, sender=MachineAssignment)
def update_machine_status_on_assign(sender, instance, created, **kwargs):
    """Auto-set machine status to 'assigned' when a new assignment is created."""
    if created:
        instance.machine.status = 'assigned'
        instance.machine.save()


# ─────────────────────────────────────────────
# FINANCIAL MANAGEMENT
# ─────────────────────────────────────────────

class FinancialCategory(models.Model):
    name      = models.CharField(max_length=150, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'financial_category'
        verbose_name_plural = 'Financial Categories'

    def __str__(self):
        return self.name
    
class Donation(models.Model):
    PAYMENT_METHODS = [
        ('cash', 'Cash'),
        ('bank', 'Bank Account'),
    ]

    donor_name     = models.CharField(max_length=255)
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHODS, default='cash')
    category       = models.ForeignKey(FinancialCategory, on_delete=models.PROTECT, related_name='donations')
    date           = models.DateField()
    notes          = models.TextField(blank=True, null=True)
    created_by     = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='donations_recorded')
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_donation'
        ordering = ['-date']

    def __str__(self):
        return f"{self.donor_name} - {self.amount} DZD ({self.date})"


class ExpenseTransaction(models.Model):
    amount               = models.DecimalField(max_digits=12, decimal_places=2)
    category             = models.ForeignKey(FinancialCategory, on_delete=models.PROTECT, related_name='expenses')
    description          = models.TextField()
    date                 = models.DateField()
    created_by           = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses_recorded')
    related_donation     = models.ForeignKey(
        DrugDonation, on_delete=models.SET_NULL, null=True, blank=True, related_name='finance_transaction'
    )
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_expense'
        ordering = ['-date']

    def __str__(self):
        return f"{self.amount} DZD - {self.category} ({self.date})"


class FinancialAuditLog(models.Model):
    ACTIONS = [('create', 'Create'), ('update', 'Update'), ('delete', 'Delete')]

    user       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    action     = models.CharField(max_length=10, choices=ACTIONS)
    model_name = models.CharField(max_length=50)
    object_id  = models.IntegerField()
    details    = models.TextField(blank=True)
    timestamp  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'finance_audit_log'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.user} {self.action} {self.model_name}#{self.object_id} @ {self.timestamp}"


def log_finance_action(user, action, model_name, object_id, details=''):
    FinancialAuditLog.objects.create(
        user=user, action=action, model_name=model_name,
        object_id=object_id, details=details
    )


# Replaces the old DrugDistribution-based signal.
# Whenever a DrugDonation is recorded as an "invoice" (i.e. the org paid for it),
# automatically log it as an expense using the donation's total_price.
@receiver(post_save, sender=DrugDonation)
def create_expense_from_invoice_donation(sender, instance, created, **kwargs):
    if created and instance.donation_type == 'invoice':
        try:
            category, _ = FinancialCategory.objects.get_or_create(name='فواتير الأدوية')
            ExpenseTransaction.objects.create(
                amount=instance.total_price,
                category=category,
                description=f"فاتورة دواء تلقائية #{instance.id} - المورد: {instance.donor}",
                date=instance.donation_date,
                related_donation=instance,
            )
        except Exception:
            pass  # never block donation creation on finance bookkeeping


class WarmWinterDonation(models.Model):
    beneficiary = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name='warm_winter_donations'
    )
    date             = models.DateField()

    class Meta:
        db_table = 'warm_winter_donation'
        ordering = ['-date']

    def __str__(self):
        return f"{self.benefeciary_name} ({self.date})"