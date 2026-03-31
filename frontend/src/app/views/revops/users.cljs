(ns app.views.revops.users
  (:require [re-frame.core :as rf]
            [reagent.core :as r]
            [app.ds.layout :as layout]
            [app.ds.cards :as cards]
            [app.ds.table :as tbl]
            [app.ds.badge :as badge]
            [app.ds.buttons :as btn]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.tokens :as t]
            [app.views.revops.dashboard :as revops-shell]
            [app.auth.subs]))

(def role-options
  [{:value "EV"      :label "EV (Executivo de Vendas)"}
   {:value "CN"      :label "CN (Consultor de Negócios)"}
   {:value "GERENTE" :label "Gerente"}
   {:value "FINANCE" :label "Financeiro"}
   {:value "ADMIN"   :label "Admin (RevOps)"}])

(def role-badge-variant
  {"EV"      :success
   "CN"      :warning
   "GERENTE" :info
   "FINANCE" :info
   "ADMIN"   :default})

(defn empty-form [] {:name "" :email "" :role "" :team_id ""})

(defn user-modal [{:keys [open? on-close user-data teams]}]
  (let [form (r/atom (or user-data (empty-form)))]
    (fn []
      (let [editing? (some? (:id user-data))]
        [modal/modal {:open?    open?
                      :on-close on-close
                      :title    (if editing? "Editar Usuário" "Novo Usuário")
                      :size     :md}
         [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
          [inputs/input
           {:label     "Nome"
            :value     (:name @form)
            :required  true
            :on-change #(swap! form assoc :name %)}]
          [inputs/input
           {:label     "E-mail"
            :value     (:email @form)
            :type      "email"
            :required  true
            :on-change #(swap! form assoc :email %)}]
          [inputs/select
           {:label     "Role"
            :value     (:role @form)
            :options   role-options
            :required  true
            :on-change #(swap! form assoc :role %)}]
          [inputs/select
           {:label     "Time"
            :value     (or (:team_id @form) "")
            :options   (into [{:value "" :label "Sem time"}]
                             (map #(hash-map :value (str (:id %)) :label (:name %))
                                  (or teams [])))
            :on-change #(swap! form assoc :team_id %)}]
          [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
           [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
           [btn/button
            {:variant  :primary
             :disabled (or (clojure.string/blank? (:name @form))
                           (clojure.string/blank? (:email @form))
                           (clojure.string/blank? (:role @form)))
             :on-click (fn []
                         (if editing?
                           (rf/dispatch [:revops/update-user (:id user-data) @form])
                           (rf/dispatch [:revops/create-user @form]))
                         (on-close))}
            (if editing? "Salvar" "Criar")]]]]))))

(defn users-page []
  (rf/dispatch [:revops/fetch-users])
  (rf/dispatch [:revops/fetch-teams])
  (let [modal-open?  (r/atom false)
        editing-user (r/atom nil)
        user-columns [{:key :name  :label "Nome"  :sortable true}
                      {:key :email :label "E-mail" :sortable false}
                      {:key :role  :label "Role"  :sortable false  :width "120px"
                       :render (fn [row]
                                 [badge/badge
                                  {:variant (get role-badge-variant (:role row) :default)}
                                  (:role row)])}
                      {:key :team_name :label "Time" :sortable false}
                      {:key :actions   :label ""    :sortable false  :width "120px"
                       :render (fn [row]
                                 [:div {:style {:display "flex" :gap "6px"}}
                                  [btn/button {:variant :ghost :size :sm
                                               :on-click #(do (reset! editing-user row)
                                                              (reset! modal-open? true))}
                                   "Editar"]
                                  [btn/button {:variant :danger :size :sm
                                               :on-click #(when (js/confirm (str "Remover " (:name row) "?"))
                                                            (rf/dispatch [:revops/delete-user (:id row)]))}
                                   "Remover"]])}]]
    (fn []
      (let [users    @(rf/subscribe [:revops/users])
            teams    @(rf/subscribe [:revops/teams])
            loading? @(rf/subscribe [:revops/users-loading?])
            user     @(rf/subscribe [:auth/current-user])
            route    @(rf/subscribe [:current-route-name])]
        [layout/page-shell
         {:sidebar-items revops-shell/sidebar-items
          :current-route route
          :user          user
          :title         "Usuários"
          :subtitle      "Gerenciar usuários da plataforma"
          :header-actions
          [btn/button
           {:variant  :primary
            :on-click #(do (reset! editing-user nil)
                           (reset! modal-open? true))}
           "+ Novo Usuário"]}

         [cards/card {}
          [tbl/data-table
           {:columns       user-columns
            :rows          (or users [])
            :empty-message (if loading? "Carregando..." "Nenhum usuário encontrado")}]]

         [user-modal {:open?     @modal-open?
                       :on-close  #(reset! modal-open? false)
                       :user-data @editing-user
                       :teams     teams}]]))))
