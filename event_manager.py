# ... (начало файла без изменений, до класса DashboardView)

# ==================== ПАНЕЛЬ УПРАВЛЕНИЯ ====================
class DashboardView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        features = {
            "ai_enabled": ("🤖 AI-чат", discord.ButtonStyle.green, discord.ButtonStyle.red),
            "monitor_enabled": ("🛡️ Мониторинг", discord.ButtonStyle.green, discord.ButtonStyle.red)
        }
        for feature, (label, on_style, off_style) in features.items():
            status = get_status(feature, True)
            style = on_style if status else off_style
            button_label = f"{label}: {'ВКЛ' if status else 'ВЫКЛ'}"
            button = ui.Button(label=button_label, style=style, custom_id=f"toggle_{feature}")
            button.callback = self.make_callback(feature)
            self.add_item(button)

        restart_button = ui.Button(label="🔄 Перезапустить бота", style=discord.ButtonStyle.danger, custom_id="restart_bot")
        restart_button.callback = self.restart_callback
        self.add_item(restart_button)

    def make_callback(self, feature):
        async def callback(interaction: discord.Interaction):
            if not has_moderator_role(interaction.user):
                await interaction.response.send_message("❌ У вас недостаточно прав для управления панелью.", ephemeral=True)
                logger.warning(f"Пользователь {interaction.user} пытался управлять панелью без прав")
                return
            current = get_status(feature, True)
            new_status = not current
            set_status(feature, new_status)
            self.update_buttons()
            embed = discord.Embed(
                title="📋 Панель управления ботом",
                description="Управляйте функциями бота через кнопки ниже. Статус каждой функции отображается на кнопке.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Статус", value="Зелёный – включено, Красный – выключено", inline=False)
            embed.set_footer(text="G4S Командование")
            await interaction.response.edit_message(embed=embed, view=self)
            logger.info(f"Пользователь {interaction.user} переключил {feature} в {'ВКЛ' if new_status else 'ВЫКЛ'}")
        return callback

    async def restart_callback(self, interaction: discord.Interaction):
        if not has_moderator_role(interaction.user):
            await interaction.response.send_message("❌ У вас недостаточно прав для перезапуска бота.", ephemeral=True)
            logger.warning(f"Пользователь {interaction.user} пытался перезапустить бота без прав")
            return
        await interaction.response.send_modal(RestartConfirmModal())

# ... (остальной код файла без изменений)
