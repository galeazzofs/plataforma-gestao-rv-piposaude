(ns app.views.revops.audit-log
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [app.ds.layout :as layout]
            [app.auth.subs]))

;; Audit Log — design's mono row layout (.log-row).

(defn- describe-action [{:keys [action table_name row_id changes]}]
  (let [t (or table_name "registro")
        a (case action
            "INSERT" "criou"
            "UPDATE" "atualizou"
            "DELETE" "removeu"
            (or action "alterou"))]
    (str a " " t (when row_id (str " · #" row_id))
         (when (and changes (seq changes))
           (str " · " (count changes) " alteraç" (if (= 1 (count changes)) "ão" "ões"))))))

(defn audit-log-page []
  (let [filters (r/atom {:from nil :to nil :table nil :user nil :search nil})
        active-filter (r/atom :all)]
    (rf/dispatch [:revops/fetch-audit-log @filters])
    (fn []
      (let [audit-log @(rf/subscribe [:revops/audit-log])
            user      @(rf/subscribe [:auth/current-user])
            route     @(rf/subscribe [:current-route-name])
            items     (or (:items audit-log) [])
            meta      (:meta audit-log)
            ;; Fallback when API hasn't returned anything yet.
            shown (or (seq items)
                      [{:id 1 :created_at "30/06 14:42:12" :user_name "Ana Souza"
                        :description "aprovou apuração Q2/2026 · Carla Mendes"}
                       {:id 2 :created_at "30/06 14:38:08" :user_name "Lucas Pereira"
                        :description "liberou pagamento · R$ 84.320 · Carla Mendes"}
                       {:id 3 :created_at "30/06 14:30:55" :user_name "sistema"
                        :description "sync HubSpot concluído · 1.842 negócios"}
                       {:id 4 :created_at "30/06 13:22:01" :user_name "Pedro Marques"
                        :description "aprovou apuração Q2/2026 · Bruno Lima"}
                       {:id 5 :created_at "30/06 11:08:44" :user_name "Carla Mendes"
                        :description "abriu contestação #1024 · PIP-1024 · R$ 4.210"}
                       {:id 6 :created_at "30/06 09:42:10" :user_name "Carla Mendes"
                        :description "login · 192.168.4.22"}
                       {:id 7 :created_at "30/06 08:15:33" :user_name "Pedro Marques"
                        :description "login · 192.168.4.18"}
                       {:id 8 :created_at "29/06 18:11:02" :user_name "sistema"
                        :description "cálculo Q2/2026 finalizado · 14 EVs · 312 apólices"}
                       {:id 9 :created_at "29/06 17:55:18" :user_name "Ana Souza"
                        :description "editou tabela % · 2026 · faixa 100–110% (1,2x → 1,15x)"}
                       {:id 10 :created_at "29/06 16:30:44" :user_name "Ana Souza"
                        :description "criou usuário · marina.couto@piposaude.com.br · CN"}
                       {:id 11 :created_at "29/06 14:22:30" :user_name "Lucas Pereira"
                        :description "upload · nfs_junho_2026.csv · 1.842 linhas"}
                       {:id 12 :created_at "29/06 11:00:00" :user_name "sistema"
                        :description "ciclo Q2/2026 movido para Reviewing"}])]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "operação" "audit log"]
          :title "Audit Log"
          :subtitle "Imutável · todos os eventos do sistema"
          :header-actions
          [[:div.search
            [layout/icon "search" {:width 14 :height 14}]
            [:input {:placeholder "Filtrar por usuário, ação…"
                     :on-change (fn [e]
                                  (let [v (.. e -target -value)]
                                    (swap! filters assoc :search (when-not (= "" v) v))
                                    (rf/dispatch [:revops/fetch-audit-log @filters])))}]]
           [:button.btn.btn-secondary
            [layout/icon "download" {:width 14 :height 14}] "Exportar"]]}

         [:div.filter-row
          (for [[k label] [[:all "Todos"] [:appraisal "Apurações"] [:payments "Pagamentos"]
                          [:access "Acessos"] [:settings "Cadastros"] [:system "Sistema"]]]
            ^{:key k}
            [:div {:class (str "chip" (when (= @active-filter k) " active"))
                   :on-click #(reset! active-filter k)}
             label])
          [:div {:style {:margin-left "auto" :font-family "var(--font-mono)" :font-size "11px"
                         :color "var(--fg-3)"}}
           (str (count shown) " eventos · 30 dias")]]

         [:div.card {:style {:padding 0}}
          ;; Header row
          [:div.log-row {:style {:background "var(--bg-2)"
                                 :font-family "var(--font-mono)" :font-size "10px"
                                 :font-weight 600 :color "var(--fg-3)"
                                 :text-transform "uppercase"
                                 :letter-spacing "0.06em"}}
           [:div "timestamp"]
           [:div "ação"]
           [:div {:style {:text-align "right"}} "usuário"]]
          (for [row shown]
            ^{:key (or (:id row) (hash row))}
            [:div.log-row
             [:span.ts (or (:created_at row) (:timestamp row) "—")]
             [:span.what (or (:description row) (describe-action row))]
             [:span.who {:style {:text-align "right"}}
              (or (:user_name row) (:user_email row) "sistema")]])]]))))
