from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from ticket.models import TicketUser, Ticket, TicketQuota
from django.db import transaction
from ticket.utils import generate_qr_code
import random
import logging

logger = logging.getLogger('ticket')

class Command(BaseCommand):
    help = 'Generates remaining tickets to fill quotas with default user information'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chaman',
            action='store_true',
            help='Generate remaining tickets for Chaman Enclosure',
        )
        parser.add_argument(
            '--gawader',
            action='store_true',
            help='Generate remaining tickets for Gawader Enclosure',
        )
        parser.add_argument(
            '--admin-username',
            type=str,
            default='admin',
            help='Username of admin user who will be set as creator',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=0,
            help='Number of tickets to generate (default: all remaining)',
        )
        parser.add_argument(
            '--specific-count',
            type=int,
            default=0,
            help='Generate a specific number of tickets regardless of quota',
        )
        parser.add_argument(
            '--chaman-start-cnic',
            type=int,
            default=135,
            help='Starting CNIC number for Chaman Enclosure (default: 135)',
        )
        parser.add_argument(
            '--gawader-start-cnic',
            type=int,
            default=653,
            help='Starting CNIC number for Gawader Enclosure (default: 653)',
        )

    def handle(self, *args, **options):
        try:
            # Get admin user who will be set as creator
            try:
                admin_user = User.objects.get(username=options['admin_username'])
            except User.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Admin user '{options['admin_username']}' not found"))
                return
            
            # Get quotas
            try:
                chaman_quota = TicketQuota.objects.get(ticket_type=Ticket.CHAMAN_ENCLOSURE)
                gawader_quota = TicketQuota.objects.get(ticket_type=Ticket.GAWADER_ENCLOSURE)
            except TicketQuota.DoesNotExist:
                self.stdout.write(self.style.ERROR("Ticket quotas not found. Run setup_quotas command first."))
                return
            
            # Calculate remaining tickets
            chaman_remaining = chaman_quota.remaining
            gawader_remaining = gawader_quota.remaining
            
            self.stdout.write(self.style.SUCCESS(f"Current status:"))
            self.stdout.write(self.style.SUCCESS(f"Chaman Enclosure: {chaman_quota.sold_quantity} sold, {chaman_remaining} remaining"))
            self.stdout.write(self.style.SUCCESS(f"Gawader Enclosure: {gawader_quota.sold_quantity} sold, {gawader_remaining} remaining"))
            
            # If count is specified, limit the number of tickets to generate
            count_limit = options['count']
            if count_limit > 0:
                self.stdout.write(self.style.SUCCESS(f"Limiting to {count_limit} tickets per enclosure"))
                chaman_remaining = min(chaman_remaining, count_limit)
                gawader_remaining = min(gawader_remaining, count_limit)
            
            # Get starting CNIC numbers for each enclosure
            chaman_start_cnic = options['chaman_start_cnic']
            gawader_start_cnic = options['gawader_start_cnic']
            
            # Generate tickets based on options
            if options['chaman']:
                self._generate_tickets(
                    admin_user, 
                    Ticket.CHAMAN_ENCLOSURE, 
                    chaman_remaining,
                    chaman_start_cnic
                )
            
            if options['gawader']:
                self._generate_tickets(
                    admin_user, 
                    Ticket.GAWADER_ENCLOSURE, 
                    gawader_remaining,
                    gawader_start_cnic
                )
                
            if not options['chaman'] and not options['gawader']:
                self.stdout.write(self.style.WARNING("No action taken. Use --chaman or --gawader to generate tickets."))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))
            logger.error(f"Error in generate_remaining_tickets: {str(e)}")
    
    def _generate_tickets(self, admin_user, ticket_type, count, start_cnic):
        """Generate tickets for a specific enclosure"""
        self.stdout.write(self.style.SUCCESS(f"Generating {count} tickets for {ticket_type}..."))
        
        # Set price based on ticket type
        price = 4000 if ticket_type == Ticket.GAWADER_ENCLOSURE else 3000
        
        # Get quota
        quota = TicketQuota.objects.get(ticket_type=ticket_type)
        
        successful = 0
        failed = 0
        
        for i in range(count):
            try:
                with transaction.atomic():
                    # Determine gender (80% male, 20% female)
                    gender = TicketUser.FEMALE if random.random() < 0.2 else TicketUser.MALE
                    
                    # Generate CNIC starting from the specified number
                    current_cnic = start_cnic + i
                    
                    # Format CNIC with leading zeros (13 digits)
                    cnic = f"{current_cnic:013d}"
                    
                    # Use enclosure-specific naming format
                    enclosure_prefix = "CH" if ticket_type == Ticket.CHAMAN_ENCLOSURE else "GW"
                    
                    # Create user
                    user = TicketUser.objects.create(
                        full_name=f"{enclosure_prefix} Ticket Holder {current_cnic}",
                        father_name="Default",
                        cnic_number=cnic,
                        phone_number="03000000000",
                        email="default@example.com",
                        gender=gender,
                        age=30,
                        relationship=TicketUser.SELF,
                        registered_by=None  # No operator for bulk generation
                    )
                    
                    # Create ticket
                    ticket = Ticket.objects.create(
                        user=user,
                        ticket_type=ticket_type,
                        price=price,
                        status=Ticket.UNSCANNED,
                        created_by=admin_user
                    )
                    
                    # Generate QR code
                    qr_data = f"T:{ticket.ticket_id}"
                    generate_qr_code(qr_data, ticket)
                    
                    # Update quota
                    quota.sold_quantity += 1
                    quota.save()
                    
                    successful += 1
                    
                    # Print progress every 100 tickets
                    if successful % 100 == 0:
                        self.stdout.write(f"Generated {successful} tickets...")
                        
            except Exception as e:
                failed += 1
                logger.error(f"Error generating ticket: {str(e)}")
                
        self.stdout.write(self.style.SUCCESS(f"Completed: {successful} tickets generated, {failed} failed"))
        self.stdout.write(self.style.SUCCESS(f"New quota status for {ticket_type}: {quota.sold_quantity} sold, {quota.remaining} remaining"))